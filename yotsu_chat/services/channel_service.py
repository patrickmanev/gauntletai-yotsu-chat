from typing import Optional, List, Tuple, Dict
import logging
import aiosqlite
from ..utils import debug_log
from ..schemas.channel import ChannelType, ChannelRole
from .role_service import role_service
from fastapi import HTTPException
from ..utils.errors import YotsuError
from ..core.ws_core import manager as ws_manager

logger = logging.getLogger(__name__)

class ChannelService:
    def __init__(self):
        debug_log("CHANNEL", "Initializing channel service")
    
    async def create_notes_channel(self, db: aiosqlite.Connection, user_id: int) -> int:
        """Create a notes channel for a user during registration."""
        debug_log("CHANNEL", f"Creating notes channel for user {user_id}")
        try:
            async with db.execute(
                """
                INSERT INTO channels (type, created_by)
                VALUES (?, ?)
                RETURNING channel_id
                """,
                (ChannelType.NOTES, user_id)
            ) as cursor:
                channel_id = (await cursor.fetchone())[0]
            
            # Add user as the sole member
            await db.execute(
                """
                INSERT INTO channels_members (channel_id, user_id, role)
                VALUES (?, ?, ?)
                """,
                (channel_id, user_id, ChannelRole.OWNER)
            )
            
            await db.commit()
            debug_log("CHANNEL", f"Created notes channel {channel_id} for user {user_id}")
            return channel_id
            
        except Exception as e:
            logger.error(f"Failed to create notes channel for user {user_id}: {str(e)}")
            await db.rollback()
            raise
    
    async def get_or_create_dm(
        self, 
        db: aiosqlite.Connection, 
        user1_id: int, 
        user2_id: int
    ) -> Tuple[int, bool]:
        """Get existing DM channel or create new one between two users.
        Returns: (channel_id, was_created)
        """
        debug_log("CHANNEL", f"Getting/creating DM channel between users {user1_id} and {user2_id}")
        
        try:
            # Check for existing DM channel
            async with db.execute(
                """
                SELECT c.channel_id 
                FROM channels c
                JOIN channels_members cm1 ON c.channel_id = cm1.channel_id
                JOIN channels_members cm2 ON c.channel_id = cm2.channel_id
                WHERE c.type = 'dm'
                AND cm1.user_id = ?
                AND cm2.user_id = ?
                """,
                (user1_id, user2_id)
            ) as cursor:
                existing = await cursor.fetchone()
                
                if existing:
                    debug_log("CHANNEL", f"Found existing DM channel {existing['channel_id']}")
                    return existing['channel_id'], False
            
            # Create new DM channel
            async with db.execute(
                """
                INSERT INTO channels (type, created_by)
                VALUES (?, ?)
                RETURNING channel_id
                """,
                (ChannelType.DM, user1_id)
            ) as cursor:
                channel_id = (await cursor.fetchone())[0]
            
            # Add both users
            await db.execute(
                """
                INSERT INTO channels_members (channel_id, user_id)
                VALUES (?, ?), (?, ?)
                """,
                (channel_id, user1_id, channel_id, user2_id)
            )
            
            await db.commit()
            debug_log("CHANNEL", f"Created new DM channel {channel_id}")

            # Initialize WebSocket channel
            await ws_manager.initialize_channel(channel_id)
            debug_log("CHANNEL", "├─ Initialized WebSocket channel")

            # Subscribe both users' WebSocket connections to the new channel
            for connection_id, websocket in ws_manager.active_connections.items():
                user_id = ws_manager.connection_users.get(connection_id)
                if user_id in [user1_id, user2_id]:
                    debug_log("CHANNEL", f"├─ Subscribing user {user_id}'s connection {connection_id} to new DM channel {channel_id}")
                    await ws_manager.subscribe_to_updates(connection_id, channel_id)
                    debug_log("CHANNEL", f"└─ Subscribed user {user_id}'s connection {connection_id}")

            # NEW CODE: Broadcast member.joined for each participant
            debug_log("CHANNEL", "Broadcasting member.joined event for new DM participants")
            for uid in [user1_id, user2_id]:
                member_info = await self.get_member_info(db, channel_id, uid)
                event = {
                    "type": "member.joined",
                    "data": member_info
                }
                await ws_manager.broadcast_to_subscribers(channel_id, event)
                debug_log("CHANNEL", f"│ └─ Broadcasted member.joined for user {uid}")

            return channel_id, True
            
        except Exception as e:
            logger.error(f"Failed to get/create DM channel: {str(e)}")
            await db.rollback()
            raise
    
    async def validate_users_exist(
        self,
        db: aiosqlite.Connection,
        user_ids: List[int]
    ) -> None:
        """Validate that all provided user IDs exist in the database.
        
        Args:
            db: Database connection
            user_ids: List of user IDs to validate
            
        Raises:
            ValueError: If any users don't exist, with details of invalid IDs
        """
        if not user_ids:
            return
            
        # Check if all users exist
        placeholders = ','.join('?' * len(user_ids))
        async with db.execute(
            f"""
            SELECT user_id FROM users 
            WHERE user_id IN ({placeholders})
            """,
            user_ids
        ) as cursor:
            valid_users = {row[0] for row in await cursor.fetchall()}
            
        # Find any invalid users
        invalid_users = set(user_ids) - valid_users
        if invalid_users:
            raise ValueError(f"Invalid member ID(s): {', '.join(map(str, invalid_users))}")

    async def create_channel(
        self, 
        db: aiosqlite.Connection, 
        name: str,
        type: ChannelType,
        created_by: int,
        initial_members: Optional[List[int]] = None
    ) -> int:
        """Create a new public/private channel.
        
        Args:
            name: Channel name (already validated by schema)
            type: Channel type (already validated by schema)
            created_by: User ID of channel creator
            initial_members: Optional list of user IDs to add as members
            
        Returns:
            channel_id: ID of created channel
            
        Raises:
            ValueError: If any initial members don't exist
        """
        debug_log("CHANNEL", f"Creating {type} channel '{name}' by user {created_by}")
        
        try:
            # Verify creator exists
            await self.verify_user_exists(db, created_by)
            
            # Verify initial members exist if provided
            if initial_members:
                for member_id in initial_members:
                    await self.verify_user_exists(db, member_id)
                
                # Check for duplicates in initial_members
                if len(initial_members) != len(set(initial_members)):
                    raise ValueError("Duplicate members are not allowed")
            
            # Create channel
            async with db.execute(
                """
                INSERT INTO channels (name, type, created_by)
                VALUES (?, ?, ?)
                RETURNING channel_id
                """,
                (name, type, created_by)
            ) as cursor:
                channel_id = (await cursor.fetchone())[0]
            
            # Add creator
            if type == ChannelType.PRIVATE:
                # For private channels, creator is owner
                await db.execute(
                    """
                    INSERT INTO channels_members (channel_id, user_id, role)
                    VALUES (?, ?, ?)
                    """,
                    (channel_id, created_by, ChannelRole.OWNER)
                )
            else:
                # For public channels, no roles
                await db.execute(
                    """
                    INSERT INTO channels_members (channel_id, user_id)
                    VALUES (?, ?)
                    """,
                    (channel_id, created_by)
                )
            
            await db.commit()
            debug_log("CHANNEL", f"Created channel {channel_id}")
            
            # Subscribe creator's WebSocket connections to the channel
            debug_log("CHANNEL", f"├─ Attempting to subscribe creator {created_by} to channel {channel_id}")
            debug_log("CHANNEL", f"├─ Active connections: {list(ws_manager.active_connections.keys())}")
            debug_log("CHANNEL", f"├─ Connection users: {ws_manager.connection_users}")
            
            for connection_id, websocket in ws_manager.active_connections.items():
                debug_log("CHANNEL", f"├─ Checking connection {connection_id}")
                user_id = ws_manager.connection_users.get(connection_id)
                debug_log("CHANNEL", f"├─ Connection {connection_id} belongs to user {user_id}")
                if user_id == created_by:
                    await ws_manager.subscribe_to_updates(connection_id, channel_id)
                    debug_log("CHANNEL", f"└─ Subscribed connection {connection_id} to channel {channel_id}")
            
            # Add initial members if provided
            if initial_members:
                # Filter out creator as they're already added
                members_to_add = [m for m in initial_members if m != created_by]
                # Remove duplicates while preserving order
                members_to_add = list(dict.fromkeys(members_to_add))
                
                for member_id in members_to_add:
                    try:
                        await self.add_member(db, channel_id, member_id, created_by)
                    except HTTPException as e:
                        if e.status_code == 400 and "already a member" in str(e.detail):
                            # Skip already added members
                            continue
                        raise
            
            return channel_id
            
        except Exception as e:
            logger.error(f"Failed to create channel: {str(e)}")
            await db.rollback()
            raise
    
    async def list_channels(
        self,
        db: aiosqlite.Connection,
        user_id: int,
        include_types: Optional[List[str]] = None,
        limit: Optional[int] = None
    ) -> List[Dict]:
        """List channels for a user.
        
        Args:
            db: Database connection
            user_id: User ID to list channels for
            include_types: Optional list of channel types to include
            limit: Optional limit on number of channels to return
            
        Returns:
            List of channels the user has access to
        """
        debug_log("CHANNEL", f"Listing channels for user {user_id}")
        
        try:
            # Build base query
            query = """
                SELECT DISTINCT
                    c.channel_id,
                    c.name,
                    c.type,
                    CASE 
                        WHEN c.type = 'private' THEN cm.role
                        ELSE NULL
                    END as role,
                    c.created_at,
                    c.created_by,
                    EXISTS(
                        SELECT 1 FROM channels_members 
                        WHERE channel_id = c.channel_id 
                        AND user_id = ?
                    ) as is_member
                FROM channels c
                LEFT JOIN channels_members cm ON c.channel_id = cm.channel_id AND cm.user_id = ?
                WHERE (
                    c.type = 'public'
                    OR EXISTS(
                        SELECT 1 FROM channels_members 
                        WHERE channel_id = c.channel_id 
                        AND user_id = ?
                    )
                )
            """
            params = [user_id, user_id, user_id]  # Three placeholders in base query
            
            # Add type filter if specified
            if include_types:
                placeholders = ",".join("?" * len(include_types))
                query += f" AND c.type IN ({placeholders})"
                # Convert enum values to strings if needed
                params.extend(t.value if hasattr(t, 'value') else t for t in include_types)
            
            # Add ordering
            query += " ORDER BY c.name ASC"
            
            # Add limit if specified
            if limit:
                query += " LIMIT ?"
                params.append(limit)
            
            # Execute query
            debug_log("CHANNEL", f"├─ Query params: {params}")
            async with db.execute(query, params) as cursor:
                # Get column names from cursor description
                columns = [col[0] for col in cursor.description]
                rows = await cursor.fetchall()
                # Convert rows to dictionaries with proper column names
                channels = [dict(zip(columns, row)) for row in rows]
                debug_log("CHANNEL", f"└─ Found {len(channels)} channels")
                return channels
            
        except Exception as e:
            logger.error(f"Failed to list channels: {str(e)}")
            raise
    
    async def list_public_channels(
        self,
        db: aiosqlite.Connection,
        user_id: int,
        search: Optional[str] = None,
        offset: int = 0,
        limit: int = 50
    ) -> Tuple[List[dict], int]:
        """List all public channels with optional search and pagination."""
        debug_log("CHANNEL", f"Listing public channels, search={search}, offset={offset}, limit={limit}")
        
        try:
            # Base query for both count and results
            base_query = """
                FROM channels c
                LEFT JOIN channels_members cm ON c.channel_id = cm.channel_id AND cm.user_id = ?
                WHERE c.type = ?
            """
            params = [user_id, ChannelType.PUBLIC.value]
            
            if search:
                base_query += " AND c.name LIKE ?"
                params.append(f"%{search}%")
            
            # Get total count
            count_query = f"SELECT COUNT(DISTINCT c.channel_id) {base_query}"
            async with db.execute(count_query, params) as cursor:
                total_count = (await cursor.fetchone())[0]
            
            # Get paginated results
            query = f"""
                SELECT DISTINCT
                    c.channel_id,
                    c.name,
                    'public' as type,
                    c.created_at,
                    c.created_by,
                    NULL as role,
                    CASE WHEN cm.user_id IS NOT NULL THEN 1 ELSE 0 END as is_member
                {base_query}
                ORDER BY c.name ASC
                LIMIT ? OFFSET ?
            """
            # Add params again for the second query
            params = [user_id, ChannelType.PUBLIC.value]
            if search:
                params.append(f"%{search}%")
            params.extend([limit, offset])
            
            async with db.execute(query, params) as cursor:
                # Convert rows to dicts with proper column names
                columns = [col[0] for col in cursor.description]
                channels = []
                async for row in cursor:
                    channel = dict(zip(columns, row))
                    # Convert boolean fields
                    channel["is_member"] = bool(channel["is_member"])
                    # Ensure role is None for public channels
                    channel["role"] = None
                    channels.append(channel)
            
            debug_log("CHANNEL", f"Found {len(channels)} public channels")
            return channels, total_count
            
        except Exception as e:
            debug_log("ERROR", f"Failed to list public channels: {str(e)}", exc_info=True)
            raise
    
    async def verify_user_exists(
        self,
        db: aiosqlite.Connection,
        user_id: int
    ) -> None:
        """Verify that a user exists in the database.
        
        Args:
            db: Database connection
            user_id: User ID to verify
            
        Raises:
            ValueError: If the user does not exist
        """
        async with db.execute(
            "SELECT 1 FROM users WHERE user_id = ?",
            (user_id,)
        ) as cursor:
            if not await cursor.fetchone():
                raise ValueError(f"User {user_id} does not exist")

    async def add_member(
        self,
        db: aiosqlite.Connection,
        channel_id: int,
        user_id: int,
        current_user_id: int
    ) -> dict:
        """Add a member to a channel.
        
        For public channels:
        - Any member can add new members
        
        For private channels:
        - Only owners and admins can add members
        
        Raises:
            ValueError: If the user is already a member or if the user does not exist
            HTTPException: If the user lacks permission to add members
            
        Returns:
            Dict containing member info
        """
        try:
            # Verify user exists first
            await self.verify_user_exists(db, user_id)

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
                await role_service.validate_member_addition(
                    db, channel_id, current_user_id
                )
                debug_log("CHANNEL", "├─ Permission validation successful")
            
            # Check if user is already a member
            async with db.execute(
                """SELECT 1 FROM channels_members 
                WHERE channel_id = ? AND user_id = ?""",
                (channel_id, user_id)
            ) as cursor:
                if await cursor.fetchone():
                    debug_log("CHANNEL", "└─ User is already a member")
                    raise HTTPException(status_code=400, detail="User is already a member")
            
            debug_log("CHANNEL", "├─ Starting member addition")
            # Add member
            if channel_type == ChannelType.PRIVATE:
                await db.execute(
                    """INSERT INTO channels_members (channel_id, user_id, role)
                    VALUES (?, ?, ?)""",
                    (channel_id, user_id, ChannelRole.MEMBER)
                )
            else:
                await db.execute(
                    """INSERT INTO channels_members (channel_id, user_id)
                    VALUES (?, ?)""",
                    (channel_id, user_id)
                )
            await db.commit()
            
            debug_log("CHANNEL", f"└─ Added user {user_id} to channel {channel_id}")
            
            # Subscribe all user's active WebSocket connections to the channel
            for connection_id in ws_manager.active_connections.items():
                if ws_manager.connection_users.get(connection_id) == user_id:
                    await ws_manager.subscribe_to_updates(connection_id, channel_id)
                    debug_log("CHANNEL", f"└─ Subscribed connection {connection_id} to channel {channel_id}")
            
            # Get member info for broadcast
            member_info = await self.get_member_info(db, channel_id, user_id)
            
            # Broadcast member.joined event
            event = {
                "type": "member.joined",
                "data": member_info
            }
            await ws_manager.broadcast_to_subscribers(channel_id, event)
            debug_log("CHANNEL", "Broadcasted member.joined event")
            
            return member_info
            
        except (HTTPException, YotsuError):
            raise
        except Exception as e:
            debug_log("ERROR", f"Failed to add channel member: {str(e)}", exc_info=True)
            raise HTTPException(status_code=500, detail="Failed to add channel member")
    
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
                    # For private channels, validate through role service first
                    await role_service.validate_member_removal(db, channel_id, target_user_id, current_user_id)
            # For private channels removing others, validate through role service
            elif channel_type == ChannelType.PRIVATE:
                await role_service.validate_member_removal(db, channel_id, target_user_id, current_user_id)
            
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
                event = {
                    "type": "member.left",
                    "data": {
                        "channel_id": channel_id,
                        "user_id": target_user_id
                    }
                }
                await ws_manager.broadcast_to_subscribers(channel_id, event)
                debug_log("CHANNEL", "Broadcasted member.left event")
            else:
                debug_log("CHANNEL", "Skipped member.left broadcast for last member (channel deleted)")
                
        except Exception as e:
            logger.error(f"Failed to remove channel member: {str(e)}")
            await db.rollback()
            raise
    
    async def get_channel_members(
        self,
        db: aiosqlite.Connection,
        channel_id: int
    ) -> List[dict]:
        """Get all members of a channel.
        
        Only works for public and private channels.
        For private channels, includes role information and orders by role.
        For public channels, no roles are included.
        
        Args:
            db: Database connection
            channel_id: Channel ID to get members for
            
        Returns:
            List of members with their roles (private only), display names, and joined_at
            
        Raises:
            ValueError: If channel is not found or is not a public/private channel
        """
        debug_log("CHANNEL", f"Getting members for channel {channel_id}")
        
        try:
            # First check channel type
            async with db.execute(
                "SELECT type FROM channels WHERE channel_id = ?",
                [channel_id]
            ) as cursor:
                result = await cursor.fetchone()
                if not result:
                    raise ValueError("Channel not found")
                
                channel_type = result[0]  # Access by index since it's a tuple
                if channel_type not in [ChannelType.PUBLIC, ChannelType.PRIVATE]:
                    raise ValueError("Can only list members for public/private channels")

            # Build query based on channel type
            if channel_type == ChannelType.PRIVATE:
                query = """
                    SELECT 
                        cm.user_id,
                        u.display_name,
                        cm.role,
                        cm.joined_at
                    FROM channels_members cm
                    JOIN users u ON cm.user_id = u.user_id
                    WHERE cm.channel_id = ?
                    ORDER BY 
                        CASE 
                            WHEN cm.role = 'owner' THEN 1
                            WHEN cm.role = 'admin' THEN 2
                            ELSE 3
                        END,
                        u.display_name
                """
            else:  # Public channel
                query = """
                    SELECT 
                        cm.user_id,
                        u.display_name,
                        NULL as role,
                        cm.joined_at
                    FROM channels_members cm
                    JOIN users u ON cm.user_id = u.user_id
                    WHERE cm.channel_id = ?
                    ORDER BY u.display_name
                """
            
            async with db.execute(query, [channel_id]) as cursor:
                # Get column names from cursor description
                columns = [col[0] for col in cursor.description]
                rows = await cursor.fetchall()
                # Convert rows to dictionaries with proper column names
                members = [dict(zip(columns, row)) for row in rows]
            
            debug_log("CHANNEL", f"Found {len(members)} members for channel {channel_id}")
            return members
            
        except Exception as e:
            logger.error(f"Failed to get channel members: {str(e)}")
            raise
    
    async def get_member_info(
        self,
        db: aiosqlite.Connection,
        channel_id: int,
        user_id: int
    ) -> Optional[dict]:
        """Get member information including role (for private channels only)."""
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
            return dict(row) if row else None
    
    async def update_channel(
        self,
        db: aiosqlite.Connection,
        channel_id: int,
        name: str,
        current_user_id: int
    ) -> dict:
        """Update channel metadata (name)."""
        debug_log("CHANNEL", f"Updating channel {channel_id}")
        debug_log("CHANNEL", f"├─ New name: {name}")
        debug_log("CHANNEL", f"├─ Current user: {current_user_id}")
        
        try:
            # First check if channel exists and get its type
            async with db.execute(
                "SELECT type FROM channels WHERE channel_id = ?",
                [channel_id]
            ) as cursor:
                result = await cursor.fetchone()
                if not result:
                    debug_log("CHANNEL", "└─ Channel not found")
                    raise HTTPException(status_code=404, detail="Channel not found")
                
                channel_type = result["type"]
                debug_log("CHANNEL", f"├─ Channel type: {channel_type}")
            
            # Cannot update DM or Notes channels
            if channel_type in [ChannelType.DM, ChannelType.NOTES]:
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot update {channel_type} channels"
                )
            
            # Check if name already exists (do this before channel type check)
            async with db.execute(
                """
                SELECT 1 FROM channels 
                WHERE name = ? AND channel_id != ?
                """,
                (name, channel_id)
            ) as cursor:
                if await cursor.fetchone():
                    debug_log("CHANNEL", "└─ Channel name already exists")
                    raise HTTPException(
                        status_code=400,
                        detail="A channel with this name already exists"
                    )
            
            # Only private channels can be updated
            if channel_type != ChannelType.PRIVATE:
                raise HTTPException(
                    status_code=422,
                    detail=[{"msg": "Only private channel names can be updated"}]
                )

            # Now check membership and role
            channel_info = await self.get_member_info(db, channel_id, current_user_id)
            if not channel_info:
                debug_log("CHANNEL", "└─ User not a member")
                raise HTTPException(status_code=404, detail="Channel not found")
            
            user_role = channel_info["role"]
            debug_log("CHANNEL", f"├─ User role: {user_role}")
            
            # For private channels, only owners can update
            if user_role != ChannelRole.OWNER:
                raise HTTPException(
                    status_code=403,
                    detail="Only channel owners can update private channels"
                )
            
            # Update channel name
            await db.execute(
                """
                UPDATE channels
                SET name = ?
                WHERE channel_id = ?
                """,
                (name, channel_id)
            )
            await db.commit()
            
            debug_log("CHANNEL", "├─ Channel updated successfully")
            
            # Broadcast channel update event
            event = {
                "type": "channel.update",
                "data": {
                    "channel_id": channel_id,
                    "name": name
                }
            }
            await ws_manager.broadcast_to_subscribers(channel_id, event)
            debug_log("CHANNEL", "├─ Broadcasted channel update event")
            
            # Return updated channel info
            channels = await self.list_channels(
                db=db,
                user_id=current_user_id,
                include_types=[channel_type]
            )
            
            for channel in channels:
                if channel["channel_id"] == channel_id:
                    debug_log("CHANNEL", "└─ Returning updated channel info")
                    return channel
            
            raise HTTPException(status_code=500, detail="Failed to get updated channel")
            
        except HTTPException:
            raise
        except Exception as e:
            debug_log("ERROR", f"Failed to update channel: {str(e)}", exc_info=True)
            await db.rollback()
            raise HTTPException(status_code=500, detail="Failed to update channel")
    
    async def verify_channel_type(
        self,
        db: aiosqlite.Connection,
        channel_id: int,
        user_id: Optional[int] = None
    ) -> ChannelType:
        """Verify channel exists and get its type.
        
        If user_id is provided and channel is private, also verifies membership.
        Returns 404 for both non-existent channels and private channels where user is not a member.
        Public channels are accessible to all users.
        
        Args:
            db: Database connection
            channel_id: Channel ID to check
            user_id: Optional user ID to verify membership for private channels
            
        Returns:
            ChannelType of the channel
            
        Raises:
            HTTPException(404): If channel not found or user lacks access to private channel
            HTTPException(400): If channel type is invalid
        """
        debug_log("CHANNEL", f"Verifying channel {channel_id}")
        
        try:
            async with db.execute(
                "SELECT type FROM channels WHERE channel_id = ?",
                [channel_id]
            ) as cursor:
                result = await cursor.fetchone()
                if not result:
                    debug_log("CHANNEL", "└─ Channel not found")
                    raise HTTPException(status_code=404, detail="Channel not found")
                
                channel_type = result["type"]
                debug_log("CHANNEL", f"├─ Channel type: {channel_type}")
                
                # For private channels, verify membership if user_id provided
                if channel_type == ChannelType.PRIVATE and user_id is not None:
                    async with db.execute(
                        "SELECT 1 FROM channels_members WHERE channel_id = ? AND user_id = ?",
                        [channel_id, user_id]
                    ) as cursor:
                        if not await cursor.fetchone():
                            debug_log("CHANNEL", "└─ User is not a member of private channel")
                            raise HTTPException(status_code=404, detail="Channel not found")
                
                debug_log("CHANNEL", "└─ Verification successful")
                return ChannelType(channel_type)
                
        except HTTPException:
            raise
        except Exception as e:
            debug_log("ERROR", f"Failed to verify channel: {str(e)}")
            raise HTTPException(status_code=400, detail="Invalid channel type")
    
    async def is_channel_member(
        self,
        db: aiosqlite.Connection,
        channel_id: int,
        user_id: int
    ) -> bool:
        """Check if a user is a member of a channel.
        
        Args:
            db: Database connection
            channel_id: Channel ID to check
            user_id: User ID to check
            
        Returns:
            bool: True if user is a member, False otherwise
        """
        debug_log("CHANNEL", f"Checking if user {user_id} is member of channel {channel_id}")
        
        try:
            async with db.execute(
                "SELECT 1 FROM channels_members WHERE channel_id = ? AND user_id = ?",
                [channel_id, user_id]
            ) as cursor:
                result = await cursor.fetchone()
                is_member = bool(result)
                debug_log("CHANNEL", f"└─ Is member: {is_member}")
                return is_member
                
        except Exception as e:
            debug_log("ERROR", f"Failed to check channel membership: {str(e)}")
            raise HTTPException(status_code=500, detail="Failed to check channel membership")

# Global instance
channel_service = ChannelService() 