from typing import List, Union
import logging
import aiosqlite
from fastapi import HTTPException

from ..utils import debug_log
from ..utils.errors import YotsuError, raise_forbidden
from ..utils.validation import verify_users_exist
from ..schemas.channel import ChannelType, ChannelRole
from ..core.ws_core import manager as ws_manager
from ..core.ws_events import create_event, MemberEventData

logger = logging.getLogger(__name__)

class MemberService:
    def __init__(self):
        debug_log("MEMBER", "Initializing member service")
        
    async def verify_channel_type(self, db: aiosqlite.Connection, channel_id: int) -> str:
        """Get and verify channel type."""
        async with db.execute(
            "SELECT type FROM channels WHERE channel_id = ?",
            [channel_id]
        ) as cursor:
            result = await cursor.fetchone()
            if not result:
                raise ValueError("Channel not found")
            return result[0]
            
    async def is_channel_member(self, db: aiosqlite.Connection, channel_id: int, user_id: int) -> bool:
        """Check if a user is a member of a channel."""
        async with db.execute(
            "SELECT 1 FROM channels_members WHERE channel_id = ? AND user_id = ?",
            [channel_id, user_id]
        ) as cursor:
            return bool(await cursor.fetchone())

    async def add_members(
        self,
        db: aiosqlite.Connection,
        channel_id: int,
        user_ids: Union[int, List[int]],
        current_user_id: int,
        skip_broadcast: bool = False  # Added to support initial member addition
    ) -> List[dict]:
        """Add one or more members to a channel.
        
        For public channels:
        - Users can add themselves
        - Existing members can add other users
        
        For private channels:
        - Only owners and admins can add members
        
        Args:
            user_ids: Single user ID or list of user IDs to add
            skip_broadcast: If True, skip broadcasting member.joined event
                          Used during channel creation when we send channel.init instead
        
        Returns:
            List of member info dicts for added members
            
        Raises:
            HTTPException: If validation fails, user lacks permission, or unexpected error occurs
        """
        try:
            # Convert single user_id to list for consistent handling
            user_ids_list = [user_ids] if isinstance(user_ids, int) else user_ids
            if not user_ids_list:
                return []

            # Check for duplicate users in the input list first
            if len(user_ids_list) != len(set(user_ids_list)):
                raise HTTPException(
                    status_code=400,
                    detail="Cannot add duplicate users"
                )

            # Verify all users exist first
            missing_users = await verify_users_exist(db, user_ids_list)
            if missing_users:
                debug_log("CHANNEL", f"└─ Users {missing_users} do not exist")
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot add non-existent users: {missing_users}"
                )

            # Get channel type
            channel_type = await self.verify_channel_type(db, channel_id)

            # Check channel type restrictions first
            if channel_type == ChannelType.NOTES:
                debug_log("CHANNEL", "└─ Cannot add members to notes channels")
                raise HTTPException(
                    status_code=400,
                    detail="Can only add members to public/private channels"
                )
            elif channel_type == ChannelType.DM:
                debug_log("CHANNEL", "└─ Cannot add members to DM channels")
                raise HTTPException(status_code=400, detail="Cannot add members to DM channels")

            # For private channels, validate permissions
            if channel_type == ChannelType.PRIVATE:
                debug_log("CHANNEL", "├─ Validating private channel permissions")
                # Get current user's role
                async with db.execute(
                    "SELECT role FROM channels_members WHERE channel_id = ? AND user_id = ?",
                    [channel_id, current_user_id]
                ) as cursor:
                    result = await cursor.fetchone()
                    if not result:
                        debug_log("CHANNEL", "└─ User is not a member")
                        raise_forbidden("Not authorized to add members to this channel")
                    current_role = result[0]
                    
                # Only owners and admins can add members
                if current_role not in [ChannelRole.OWNER, ChannelRole.ADMIN]:
                    debug_log("CHANNEL", "└─ User lacks required role")
                    raise_forbidden("Only owners and admins can add members to private channels")
                debug_log("CHANNEL", "├─ Permission validation successful")

            # For public channels, validate that requester is either:
            # 1. Adding themselves, or
            # 2. Already a member
            elif channel_type == ChannelType.PUBLIC:
                debug_log("CHANNEL", "├─ Validating public channel permissions")
                # First check if user is already a member
                is_member = await self.is_channel_member(db, channel_id, current_user_id)
                
                # Non-members can only add themselves
                if not is_member:
                    # Fail if either:
                    # 1. Trying to add multiple users, or
                    # 2. Not adding themselves
                    if len(user_ids_list) > 1 or user_ids_list[0] != current_user_id:
                        debug_log("CHANNEL", "└─ Non-member cannot add others to channel")
                        raise_forbidden("Must be a member to add others to this channel")
                    debug_log("CHANNEL", "├─ Non-member adding themselves")
                else:
                    debug_log("CHANNEL", "├─ Member adding others")
                
                debug_log("CHANNEL", "├─ Permission validation successful")

            # Check if any users are already members
            debug_log("CHANNEL", "├─ Checking for existing members")
            placeholders = ','.join('?' * len(user_ids_list))
            async with db.execute(
                f"""SELECT user_id FROM channels_members 
                WHERE channel_id = ? AND user_id IN ({placeholders})""",
                [channel_id, *user_ids_list]
            ) as cursor:
                existing_members = {row[0] for row in await cursor.fetchall()}
                if existing_members:
                    raise HTTPException(
                        status_code=400, 
                        detail=f"Users {existing_members} are already members"
                    )

            debug_log("CHANNEL", "├─ Starting member addition")
            # Add members in a batch
            if channel_type == ChannelType.PRIVATE:
                await db.executemany(
                    """INSERT INTO channels_members (channel_id, user_id, role)
                    VALUES (?, ?, ?)""",
                    [(channel_id, user_id, ChannelRole.MEMBER.value) for user_id in user_ids_list]
                )
            else:
                await db.executemany(
                    """INSERT INTO channels_members (channel_id, user_id)
                    VALUES (?, ?)""",
                    [(channel_id, user_id) for user_id in user_ids_list]
                )
            await db.commit()
            
            debug_log("CHANNEL", f"└─ Added {len(user_ids_list)} user(s) to channel {channel_id}")
            
            # Subscribe all users' active WebSocket connections to the channel
            for user_id in user_ids_list:
                for connection_id, websocket in ws_manager.active_connections.items():
                    if ws_manager.connection_users.get(connection_id) == user_id:
                        await ws_manager.subscribe_to_updates(connection_id, channel_id)
                        debug_log("CHANNEL", f"└─ Subscribed connection {connection_id} to channel {channel_id}")
            
            # Get member info for all added members
            member_info_list = []
            for user_id in user_ids_list:
                member_info = await self.get_member_info(db, channel_id, user_id)
                member_info_list.append(member_info)
            
            # Broadcast member.joined event for each member (unless skipped)
            if not skip_broadcast:
                for member_info in member_info_list:
                    # Ensure all values are of the correct type
                    event_data = {
                        "channel_id": channel_id,  # Already an int from method param
                        "user_id": int(member_info["user_id"]),  # Ensure int
                        "display_name": str(member_info["display_name"]),  # Ensure str
                        "role": str(member_info["role"]) if member_info.get("role") is not None else None  # Handle None case
                    }
                    event = create_event(
                        "member.joined",
                        MemberEventData(**event_data)
                    )
                    await ws_manager.broadcast_to_subscribers(channel_id, event)
                    debug_log("CHANNEL", f"Broadcasted member.joined for user {member_info['user_id']}")
            
            return member_info_list
            
        except (HTTPException, YotsuError):
            raise
        except Exception as e:
            debug_log("ERROR", f"Failed to add channel members: {str(e)}", exc_info=True)
            raise HTTPException(status_code=500, detail="Failed to add channel members")
    
    async def remove_member(
        self,
        db: aiosqlite.Connection,
        channel_id: int,
        target_user_id: int,
        current_user_id: int
    ) -> None:
        """Remove a member from a channel.
        
        Rules:
        - Notes/DM channels: No member removal allowed
        - Public channels: Anyone can leave at any time
        - Private channels: 
            - Members can leave at any time
            - Other removals defer to role_service
            
        Channel Cleanup Behavior:
        - When the last member is removed, the channel is automatically deleted by a database trigger
        - In this case, we skip broadcasting the member.left event since there are no remaining members
        - This prevents initializing websocket state for a deleted channel
        """
        debug_log("CHANNEL", f"Removing user {target_user_id} from channel {channel_id}")
        
        try:
            # Get channel type and member count in one query
            async with db.execute("""
                SELECT c.type, (
                    SELECT COUNT(*) 
                    FROM channels_members cm 
                    WHERE cm.channel_id = c.channel_id
                ) as member_count
                FROM channels c 
                WHERE c.channel_id = ?
            """, [channel_id]) as cursor:
                result = await cursor.fetchone()
                if not result:
                    raise ValueError("Channel not found")
                
                channel_type = result["type"]
                is_last_member = result["member_count"] == 1  # 1 because target hasn't been removed yet
                
            # Basic validation
            if channel_type in [ChannelType.NOTES, ChannelType.DM]:
                raise ValueError(f"Cannot remove members from {channel_type} channels")
                
            # Self-removal (leaving) is always allowed for public/private
            if current_user_id == target_user_id:
                if channel_type == ChannelType.PRIVATE:
                    # For private channels, get current user's role
                    async with db.execute(
                        "SELECT role FROM channels_members WHERE channel_id = ? AND user_id = ?",
                        [channel_id, current_user_id]
                    ) as cursor:
                        result = await cursor.fetchone()
                        if not result:
                            debug_log("CHANNEL", "└─ User is not a member")
                            raise_forbidden("Not authorized to leave this channel")
            # For private channels removing others, validate through role checks
            elif channel_type == ChannelType.PRIVATE:
                # Get current user's role
                async with db.execute(
                    "SELECT role FROM channels_members WHERE channel_id = ? AND user_id = ?",
                    [channel_id, current_user_id]
                ) as cursor:
                    result = await cursor.fetchone()
                    if not result:
                        debug_log("CHANNEL", "└─ Current user is not a member")
                        raise_forbidden("Not authorized to remove members from this channel")
                    current_role = result[0]
                
                # Get target user's role
                async with db.execute(
                    "SELECT role FROM channels_members WHERE channel_id = ? AND user_id = ?",
                    [channel_id, target_user_id]
                ) as cursor:
                    result = await cursor.fetchone()
                    if not result:
                        debug_log("CHANNEL", "└─ Target user is not a member")
                        raise ValueError("Target user is not a member of the channel")
                    target_role = result[0]
                
                # Owners can remove anyone
                if current_role == ChannelRole.OWNER:
                    pass  # Allowed
                # Admins can only remove regular members
                elif current_role == ChannelRole.ADMIN:
                    if target_role not in [ChannelRole.MEMBER]:
                        debug_log("CHANNEL", "└─ Admin cannot remove owners/admins")
                        raise_forbidden("Admins can only remove regular members")
                # Regular members cannot remove others
                else:
                    debug_log("CHANNEL", "└─ Regular members cannot remove others")
                    raise_forbidden("Regular members cannot remove other members")
            
            # Get member info before removal for the event
            member_info = await self.get_member_info(db, channel_id, target_user_id)
            if not member_info:
                raise ValueError("User is not a member of the channel")
            
            # Remove member
            await db.execute(
                "DELETE FROM channels_members WHERE channel_id = ? AND user_id = ?",
                [channel_id, target_user_id]
            )
            await db.commit()
            debug_log("CHANNEL", f"User {target_user_id} was removed from channel {channel_id}")

            # Unsubscribe all user's active WebSocket connections from the channel
            for connection_id in ws_manager.active_connections:
                if ws_manager.connection_users.get(connection_id) == target_user_id:
                    await ws_manager.unsubscribe_from_updates(connection_id, channel_id)
                    debug_log("CHANNEL", f"└─ Unsubscribed connection {connection_id} from channel {channel_id}")

            # Only broadcast member.left if this wasn't the last member
            # If it was the last member, the channel is already deleted by the DB trigger
            if not is_last_member:
                event = create_event(
                    "member.left",
                    MemberEventData(
                        channel_id=channel_id,
                        user_id=target_user_id,
                        display_name=member_info["display_name"],
                        role=member_info["role"]
                    )
                )
                await ws_manager.broadcast_to_subscribers(channel_id, event)
                debug_log("CHANNEL", f"Broadcasted member.left for user {target_user_id}")
            else:
                debug_log("CHANNEL", "Skipped member.left broadcast for last member (channel deleted)")
                
        except Exception as e:
            logger.error(f"Failed to remove channel member: {str(e)}")
            await db.rollback()
            raise
    
    async def get_members(
        self,
        db: aiosqlite.Connection,
        channel_ids: List[int],
        requesting_user_id: int
    ) -> List[dict]:
        """Get members for multiple channels.
        
        For public channels: Anyone can view members
        For private channels: Only members can view
        For DM channels: Only participants can view
        For notes channels: Only the owner can view
        
        Args:
            db: Database connection
            channel_ids: List of channel IDs to get members for
            requesting_user_id: ID of user requesting the member list
            
        Returns:
            List of members with their roles (private only), display names, and joined_at
            
        Raises:
            ValueError: If any channel is not found
            HTTPException: If user is not authorized to view members of any channel
        """
        debug_log("CHANNEL", f"Getting members for channels {channel_ids}")
        
        try:
            # Get channel types for all requested channels
            channel_types = {}
            async with db.execute(
                """
                SELECT channel_id, type 
                FROM channels 
                WHERE channel_id IN ({})
                """.format(','.join('?' * len(channel_ids))),
                channel_ids
            ) as cursor:
                async for row in cursor:
                    channel_types[row[0]] = row[1]
            
            # Verify access rights
            for channel_id in channel_ids:
                if channel_id not in channel_types:
                    raise ValueError(f"Channel {channel_id} not found")
                    
                channel_type = channel_types[channel_id]
                if channel_type != ChannelType.PUBLIC:
                    # For non-public channels, verify membership
                    try:
                        await self.get_member_info(db, channel_id, requesting_user_id)
                    except ValueError:
                        raise_forbidden(f"Not authorized to view members of channel {channel_id}")

            # Build query to get members for all channels
            query = """
                SELECT 
                    cm.channel_id,
                    cm.user_id,
                    u.display_name,
                    CASE 
                        WHEN c.type = 'private' THEN cm.role
                        ELSE NULL
                    END as role,
                    cm.joined_at
                FROM channels_members cm
                JOIN users u ON cm.user_id = u.user_id
                JOIN channels c ON cm.channel_id = c.channel_id
                WHERE cm.channel_id IN ({})
                ORDER BY 
                    cm.channel_id,
                    CASE 
                        WHEN cm.role = 'owner' THEN 1
                        WHEN cm.role = 'admin' THEN 2
                        ELSE 3
                    END,
                    u.display_name
            """.format(','.join('?' * len(channel_ids)))
            
            async with db.execute(query, channel_ids) as cursor:
                columns = [col[0] for col in cursor.description]
                rows = await cursor.fetchall()
                members = [dict(zip(columns, row)) for row in rows]
            
            debug_log("CHANNEL", f"Found {len(members)} members across {len(channel_ids)} channels")
            return members
            
        except Exception as e:
            logger.error(f"Failed to get channel members: {str(e)}")
            raise
    
    async def get_member_info(
        self,
        db: aiosqlite.Connection,
        channel_id: int,
        user_id: int
    ) -> dict:
        """Get member information including role (for private channels only).
        
        Raises:
            ValueError: If user is not a member of the channel
        """
        async with db.execute(
            """
            SELECT 
                cm.channel_id,
                cm.user_id,
                u.display_name,
                CASE WHEN c.type = 'private' THEN cm.role ELSE NULL END as role,
                cm.joined_at,
                c.type as channel_type
            FROM channels_members cm
            JOIN users u ON cm.user_id = u.user_id
            JOIN channels c ON c.channel_id = cm.channel_id
            WHERE cm.channel_id = ? AND cm.user_id = ?
            """,
            (channel_id, user_id)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                raise ValueError("User is not a member of the channel")
            return dict(row)

    async def _initialize_channel_owner(
        self,
        db: aiosqlite.Connection,
        channel_id: int,
        owner_id: int
    ) -> dict:
        """Initialize the channel owner during channel creation.
        
        This is an internal method that should only be called during channel creation.
        It bypasses the normal permission checks since it establishes the initial ownership.
        
        Args:
            db: Database connection
            channel_id: ID of the newly created channel
            owner_id: User ID to set as owner
            
        Returns:
            Member info dict for the owner
        """
        # Add owner record
        await db.execute(
            """INSERT INTO channels_members (channel_id, user_id, role)
            VALUES (?, ?, ?)""",
            (channel_id, owner_id, ChannelRole.OWNER.value)
        )
        await db.commit()
        
        # Get and return member info
        return await self.get_member_info(db, channel_id, owner_id)

# Global instance
member_service = MemberService()