from typing import Optional, List, Tuple, Dict
import logging
import aiosqlite
from ..utils import debug_log
from ..schemas.channel import ChannelType, ChannelRole
from .member_service import member_service
from fastapi import HTTPException
from ..utils.errors import YotsuError
from ..core.ws_core import manager as ws_manager
from ..core.ws_events import create_event, MemberEventData, ChannelUpdateData, ChannelInitData

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
        """Get or create a DM channel between two users.
        
        Returns:
            Tuple of (channel_id, was_created)
            where was_created is True if a new channel was created
        """
        debug_log("CHANNEL", f"Getting/creating DM channel between users {user1_id} and {user2_id}")
        
        try:
            # First check if DM already exists
            async with db.execute(
                """
                SELECT c.channel_id
                FROM channels c
                JOIN channels_members cm1 ON c.channel_id = cm1.channel_id
                JOIN channels_members cm2 ON c.channel_id = cm2.channel_id
                WHERE c.type = ?
                AND cm1.user_id = ?
                AND cm2.user_id = ?
                """,
                (ChannelType.DM, user1_id, user2_id)
            ) as cursor:
                result = await cursor.fetchone()
                if result:
                    debug_log("CHANNEL", f"Found existing DM channel {result[0]}")
                    return result[0], False
            
            # Create new DM channel
            async with db.execute(
                """INSERT INTO channels (type, created_by)
                VALUES (?, ?)
                RETURNING channel_id""",
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

            # Broadcast member.joined for each participant
            debug_log("CHANNEL", "Broadcasting member.joined event for new DM participants")
            for uid in [user1_id, user2_id]:
                member_info = await member_service.get_member_info(db, channel_id, uid)
                event = create_event(
                    "member.joined",
                    MemberEventData(
                        channel_id=channel_id,
                        user_id=uid,
                        display_name=member_info["display_name"],
                        role=member_info["role"]
                    )
                )
                await ws_manager.broadcast_to_subscribers(channel_id, event)
                debug_log("CHANNEL", f"│ └─ Broadcasted member.joined for user {uid}")

            return channel_id, True
            
        except Exception as e:
            logger.error(f"Failed to get/create DM channel: {str(e)}")
            await db.rollback()
            raise
    
    async def create_channel(
        self,
        db: aiosqlite.Connection,
        name: str,
        channel_type: ChannelType,
        created_by: int,
        initial_members: Optional[List[int]] = None
    ) -> dict:
        """Create a new channel.
        
        Args:
            name: Channel name (required for public/private)
            channel_type: Type of channel to create
            created_by: User ID of creator
            initial_members: Optional list of user IDs to add as members
            
        Returns:
            Channel info dict
            
        Raises:
            HTTPException: If validation fails
        """
        debug_log("CHANNEL", f"Creating {channel_type} channel")
        debug_log("CHANNEL", f"├─ Name: {name}")
        debug_log("CHANNEL", f"├─ Created by: {created_by}")
        if initial_members:
            debug_log("CHANNEL", f"├─ Initial members: {initial_members}")
        
        try:
            # Validate channel type
            if channel_type not in [ChannelType.PUBLIC, ChannelType.PRIVATE]:
                raise HTTPException(
                    status_code=400,
                    detail=f"Cannot create {channel_type} channels directly"
                )
            
            # Validate name
            if not name or not name.strip():
                raise HTTPException(
                    status_code=400,
                    detail="Channel name is required"
                )
                
            # Check if name already exists
            async with db.execute(
                "SELECT 1 FROM channels WHERE name = ?",
                [name]
            ) as cursor:
                if await cursor.fetchone():
                    raise HTTPException(
                        status_code=400,
                        detail="Channel name already exists"
                    )
            
            # Create channel
            async with db.execute(
                """INSERT INTO channels (name, type, created_by)
                VALUES (?, ?, ?)
                RETURNING channel_id, created_at""",
                (name, channel_type.value, created_by)
            ) as cursor:
                row = await cursor.fetchone()
                channel_id, created_at = row
            await db.commit()
            
            debug_log("CHANNEL", f"├─ Created channel {channel_id}")
            
            # Initialize WebSocket channel
            await ws_manager.initialize_channel(channel_id)
            debug_log("CHANNEL", "├─ Initialized WebSocket channel")
            
            # Initialize creator based on channel type
            if channel_type == ChannelType.PRIVATE:
                # For private channels, creator becomes owner
                await member_service._initialize_channel_owner(
                    db=db,
                    channel_id=channel_id,
                    owner_id=created_by
                )
                debug_log("CHANNEL", "├─ Added creator as owner")
            else:
                # For public channels, creator is just a regular member
                await db.execute(
                    """INSERT INTO channels_members (channel_id, user_id)
                    VALUES (?, ?)""",
                    (channel_id, created_by)
                )
                await db.commit()
                debug_log("CHANNEL", "├─ Added creator as member")
            
            # Add initial members if provided
            if initial_members:
                debug_log("CHANNEL", "├─ Adding initial members")
                await member_service.add_members(
                    db=db,
                    channel_id=channel_id,
                    user_ids=initial_members,
                    current_user_id=created_by,
                    skip_broadcast=True  # Skip since we'll broadcast channel.init
                )
                debug_log("CHANNEL", f"├─ Added {len(initial_members)} initial members")
            
            # Get all members for the channel.init event
            all_members = await member_service.get_members(
                db=db,
                channel_ids=[channel_id],
                requesting_user_id=created_by
            )
            
            # Broadcast channel.init event
            event = create_event(
                "channel.init",
                ChannelInitData(
                    channel_id=channel_id,
                    name=name,
                    type=channel_type,
                    members=all_members
                )
            )
            await ws_manager.broadcast_to_subscribers(channel_id, event)
            debug_log("CHANNEL", f"└─ Broadcasted channel.init with {len(all_members)} members")
            
            return {
                "channel_id": channel_id,
                "name": name,
                "type": channel_type,
                "created_by": created_by,
                "created_at": created_at
            }
            
        except (HTTPException, YotsuError):
            raise
        except Exception as e:
            debug_log("ERROR", f"Failed to create channel: {str(e)}", exc_info=True)
            raise HTTPException(status_code=500, detail="Failed to create channel")
    
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
            List of channel info dicts
        """
        debug_log("CHANNEL", f"Listing channels for user {user_id}")
        
        try:
            # Build base query
            query = """
                SELECT 
                    c.channel_id,
                    c.name,
                    c.type,
                    CASE 
                        WHEN c.type IN ('public', 'private') THEN c.created_at
                        ELSE NULL
                    END as created_at,
                    CASE 
                        WHEN c.type IN ('public', 'private') THEN c.created_by
                        ELSE NULL
                    END as created_by
                FROM channels c
                INNER JOIN channels_members cm ON c.channel_id = cm.channel_id 
                WHERE cm.user_id = ?
            """
            params = [user_id]  # One placeholder in base query
            
            # Add type filter if specified
            if include_types:
                placeholders = ','.join('?' * len(include_types))
                query += f" AND c.type IN ({placeholders})"
                params.extend(include_types)
            
            # Add limit if specified
            if limit:
                query += " LIMIT ?"
                params.append(limit)
            
            # Execute query
            async with db.execute(query, params) as cursor:
                columns = [col[0] for col in cursor.description]
                rows = await cursor.fetchall()
                channels = [dict(zip(columns, row)) for row in rows]
                
                debug_log("CHANNEL", f"└─ Found {len(channels)} channels")
                return channels
            
        except Exception as e:
            logger.error(f"Failed to list channels: {str(e)}")
            raise

    async def list_public_channels(
        self,
        db: aiosqlite.Connection,
        search: Optional[str] = None
    ) -> List[dict]:
        """List all public channels with optional search.
        Returns only channel_id and name for minimal response."""
        debug_log("CHANNEL", f"Listing public channels, search={search}")
        
        try:
            # Simple query to get just id and name
            query = """
                SELECT DISTINCT
                    c.channel_id,
                    c.name
                FROM channels c
                WHERE c.type = ?
            """
            params = [ChannelType.PUBLIC.value]
            
            if search:
                query += " AND c.name LIKE ?"
                params.append(f"%{search}%")
            
            query += " ORDER BY c.name ASC"  # Order alphabetically for better UX
            
            async with db.execute(query, params) as cursor:
                columns = [col[0] for col in cursor.description]
                rows = await cursor.fetchall()
                channels = [dict(zip(columns, row)) for row in rows]
            
            debug_log("CHANNEL", f"└─ Found {len(channels)} public channels")
            return channels
            
        except Exception as e:
            logger.error(f"Failed to list public channels: {str(e)}")
            raise

    async def update_channel(
        self,
        db: aiosqlite.Connection,
        channel_id: int,
        name: str,
        current_user_id: int
    ) -> dict:
        """Update channel name. Only private channel owners can update the name."""
        debug_log("CHANNEL", f"Updating channel {channel_id}")
        debug_log("CHANNEL", f"├─ New name: {name}")
        
        try:
            # Get channel type and current user's role
            async with db.execute("""
                SELECT c.type, cm.role, c.created_at, c.created_by
                FROM channels c
                LEFT JOIN channels_members cm ON c.channel_id = cm.channel_id AND cm.user_id = ?
                WHERE c.channel_id = ?
            """, [current_user_id, channel_id]) as cursor:
                result = await cursor.fetchone()
                if not result:
                    raise HTTPException(status_code=404, detail="Channel not found")
                
                channel_type = result["type"]
                user_role = result["role"]
                created_at = result["created_at"]
                created_by = result["created_by"]
                
                # Only private channels can be updated
                if channel_type != ChannelType.PRIVATE:
                    raise HTTPException(status_code=422, detail=[{"msg": "Only private channel names can be updated"}])
                
                # Only owners can update channel names
                if not user_role or user_role != ChannelRole.OWNER:
                    raise HTTPException(status_code=403, detail="Only channel owners can update the name")
            
            # Check if name already exists
            async with db.execute(
                "SELECT 1 FROM channels WHERE name = ? AND channel_id != ?",
                [name, channel_id]
            ) as cursor:
                if await cursor.fetchone():
                    raise HTTPException(status_code=422, detail=[{"msg": "Channel name already exists"}])
            
            # Update channel name
            await db.execute(
                "UPDATE channels SET name = ? WHERE channel_id = ?",
                [name, channel_id]
            )
            await db.commit()
            
            debug_log("CHANNEL", "├─ Channel updated successfully")
            
            # Broadcast channel update event
            event = create_event(
                "channel.update",
                ChannelUpdateData(
                    channel_id=channel_id,
                    name=name,
                    type=channel_type
                )
            )
            await ws_manager.broadcast_to_subscribers(channel_id, event)
            debug_log("CHANNEL", "├─ Broadcasted channel.update")
            
            # Return updated channel info directly
            debug_log("CHANNEL", "└─ Returning updated channel info")
            return {
                "channel_id": channel_id,
                "name": name,
                "type": channel_type,
                "created_at": created_at,
                "created_by": created_by
            }
            
        except HTTPException:
            raise
        except Exception as e:
            debug_log("ERROR", f"Failed to update channel: {str(e)}", exc_info=True)
            await db.rollback()
            raise HTTPException(status_code=500, detail="Failed to update channel")

# Global instance
channel_service = ChannelService() 