from datetime import datetime
import logging
from typing import List, Optional, Dict, Any
import aiosqlite

from ..core.ws_core import manager as ws_manager
from ..utils.errors import raise_forbidden
from ..utils import debug_log
from ..services.channel_service import channel_service

logger = logging.getLogger(__name__)

class MessageService:
    async def create_message(
        self,
        db: aiosqlite.Connection,
        channel_id: Optional[int],
        user_id: int,
        content: str,
        parent_id: Optional[int] = None,
        other_user_id: Optional[int] = None
    ) -> int:
        """Create a new message or thread reply.
        For DMs, if channel_id is None and other_user_id is provided,
        will create or get existing DM channel.
        """
        # Validate message parameters
        if channel_id is not None and other_user_id is not None:
            raise ValueError("Cannot specify both channel_id and recipient_id")
        if channel_id is None and other_user_id is None:
            raise ValueError("Must specify either channel_id or recipient_id")

        # Handle DM channel creation/lookup
        if channel_id is None and other_user_id is not None:
            channel_id, was_created = await channel_service.get_or_create_dm(
                db=db,
                user1_id=user_id,
                user2_id=other_user_id
            )
            debug_log("MSG", f"Using DM channel {channel_id} for message between users {user_id} and {other_user_id}")
        elif channel_id is None:
            raise ValueError("Either channel_id or other_user_id must be provided")
            
        debug_log("MSG", f"Creating message in channel {channel_id} by user {user_id}")
        
        # If this is a reply, verify parent exists and is valid
        if parent_id:
            async with db.execute(
                "SELECT channel_id, parent_id FROM messages WHERE message_id = ?",
                (parent_id,)
            ) as cursor:
                parent = await cursor.fetchone()
                if not parent:
                    raise ValueError("Parent message not found")
                if parent["channel_id"] != channel_id:
                    raise ValueError("Parent message must be in the same channel")
                if parent["parent_id"] is not None:
                    raise ValueError("Cannot reply to a reply")
        
        # Verify channel access (always require membership for creating messages)
        await self._verify_channel_access(db, channel_id, user_id, require_membership=True)
        
        # Create message
        async with db.execute(
            """
            INSERT INTO messages (channel_id, user_id, content, parent_id)
            VALUES (?, ?, ?, ?)
            RETURNING message_id
            """,
            (channel_id, user_id, content, parent_id)
        ) as cursor:
            message_id = (await cursor.fetchone())[0]
        
        await db.commit()
        
        # Get message details for WebSocket broadcast
        message_data = await self.get_message(db, message_id, user_id)
        
        # Initialize WebSocket channel if needed
        await ws_manager.initialize_channel(channel_id)
        
        # Broadcast message creation
        await ws_manager.broadcast_to_channel(
            channel_id,
            {
                "type": "message.created",
                "data": {
                    "message_id": message_id,
                    "channel_id": channel_id,
                    "content": content,
                    "user_id": user_id,
                    "parent_id": parent_id,
                    "created_at": message_data["created_at"].isoformat()
                }
            }
        )
        
        debug_log("MSG", f"Created message {message_id}")
        return message_id

    async def get_message(
        self,
        db: aiosqlite.Connection,
        message_id: int,
        user_id: int
    ) -> Dict[str, Any]:
        """Get a single message with user details."""
        debug_log("MSG", f"Fetching message {message_id}")
        
        async with db.execute(
            """
            SELECT 
                m.message_id,
                m.channel_id,
                m.user_id,
                m.content,
                m.parent_id,
                m.created_at,
                m.updated_at,
                u.display_name
            FROM messages m
            JOIN users u ON m.user_id = u.user_id
            WHERE m.message_id = ?
            """,
            (message_id,)
        ) as cursor:
            message = await cursor.fetchone()
            if not message:
                raise ValueError("Message not found")
        
        # Verify user has access to the channel
        await self._verify_channel_access(db, message["channel_id"], user_id)
        
        # Convert to dict and parse timestamps
        message_dict = dict(message)
        message_dict["created_at"] = datetime.fromisoformat(message_dict["created_at"].replace("Z", "+00:00"))
        if message_dict["updated_at"]:
            message_dict["updated_at"] = datetime.fromisoformat(message_dict["updated_at"].replace("Z", "+00:00"))
        
        return message_dict

    async def list_messages(
        self,
        db: aiosqlite.Connection,
        channel_id: int,
        user_id: int,
        before: Optional[int] = None,
        limit: int = 50,
        parent_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """List messages in a channel with pagination and thread filtering.
        
        Access control:
        - Public channels: Anyone can list messages
        - Private/DM/Notes channels: Only members can list messages
        """
        debug_log("MSG", f"Listing messages in channel {channel_id}")
        
        # Verify channel access (require_membership=False allows anyone to read public channels)
        await self._verify_channel_access(db, channel_id, user_id, require_membership=False)
        
        # Build query
        query = """
            SELECT m.*, u.display_name
            FROM messages m
            JOIN users u ON m.user_id = u.user_id
            WHERE m.channel_id = ?
        """
        params: List[Any] = [channel_id]
        
        # Filter by thread if specified
        if parent_id is not None:
            # Check if parent exists
            async with db.execute(
                "SELECT 1 FROM messages WHERE message_id = ? AND channel_id = ?",
                (parent_id, channel_id)
            ) as cursor:
                if not await cursor.fetchone():
                    raise ValueError("Parent message not found")
            
            query += " AND m.parent_id = ?"
            params.append(parent_id)
        else:
            query += " AND m.parent_id IS NULL"  # Only get top-level messages
        
        if before:
            query += " AND m.message_id < ?"
            params.append(before)
        
        query += " ORDER BY m.message_id DESC LIMIT ?"
        params.append(limit)
        
        async with db.execute(query, params) as cursor:
            messages = await cursor.fetchall()
            return [dict(msg) for msg in messages]

    async def update_message(
        self,
        db: aiosqlite.Connection,
        message_id: int,
        user_id: int,
        content: str
    ) -> Dict[str, Any]:
        """Update a message's content."""
        debug_log("MSG", f"Updating message {message_id}")
        
        # Get message and verify ownership
        message = await self.get_message(db, message_id, user_id)
        if message["user_id"] != user_id:
            raise_forbidden("Can only edit your own messages")
        
        # Update message
        await db.execute(
            """
            UPDATE messages
            SET content = ?, updated_at = CURRENT_TIMESTAMP
            WHERE message_id = ?
            """,
            (content, message_id)
        )
        await db.commit()
        
        # Get updated message for response and broadcast
        updated_message = await self.get_message(db, message_id, user_id)
        
        # Broadcast update
        await ws_manager.broadcast_to_channel(
            updated_message["channel_id"],
            {
                "type": "message.updated",
                "data": {
                    "message_id": message_id,
                    "channel_id": updated_message["channel_id"],
                    "content": content,
                    "user_id": user_id,
                    "updated_at": updated_message["updated_at"].isoformat()
                }
            }
        )
        
        return updated_message

    async def delete_message(
        self,
        db: aiosqlite.Connection,
        message_id: int,
        user_id: int
    ) -> Dict[str, str]:
        """Delete a message with proper cascade handling for threads."""
        debug_log("MSG", f"Deleting message {message_id}")
        
        async with db.cursor() as cur:
            # Get message and verify permissions
            message = await self.get_message(db, message_id, user_id)
            
            # Check if user is author or channel admin/owner
            if message["user_id"] != user_id:
                await cur.execute(
                    """
                    SELECT role FROM channels_members
                    WHERE channel_id = ? AND user_id = ?
                    """,
                    (message["channel_id"], user_id)
                )
                member = await cur.fetchone()
                if not member or member["role"] not in ["owner", "admin"]:
                    raise ValueError("No permission to delete this message")
            
            # Handle thread parent deletion
            if message["parent_id"] is None:
                await cur.execute(
                    """
                    SELECT EXISTS(
                        SELECT 1 FROM messages WHERE parent_id = ?
                    ) as has_replies
                    """,
                    (message_id,)
                )
                has_replies = (await cur.fetchone())["has_replies"]
                
                if has_replies:
                    # Soft delete thread parent
                    await cur.execute(
                        """
                        UPDATE messages 
                        SET content = 'This message was deleted',
                            updated_at = CURRENT_TIMESTAMP
                        WHERE message_id = ?
                        """,
                        (message_id,)
                    )
                    await cur.execute(
                        "DELETE FROM reactions WHERE message_id = ?",
                        (message_id,)
                    )
                    await db.commit()
                    
                    await ws_manager.broadcast_to_channel(
                        message["channel_id"],
                        {
                            "type": "message.soft_deleted",
                            "data": {
                                "message_id": message_id,
                                "channel_id": message["channel_id"]
                            }
                        }
                    )
                    return {"message": "Message marked as deleted"}
            
            # Handle reply deletion and cleanup
            if message["parent_id"]:
                await self._handle_reply_deletion(db, cur, message)
            
            # Delete message attachments and reactions
            await cur.execute("DELETE FROM reactions WHERE message_id = ?", (message_id,))
            await cur.execute("DELETE FROM attachments WHERE message_id = ?", (message_id,))
            
            # Delete the message
            await cur.execute("DELETE FROM messages WHERE message_id = ?", (message_id,))
            await db.commit()
            
            # Broadcast deletion
            await ws_manager.broadcast_to_channel(
                message["channel_id"],
                {
                    "type": "message.deleted",
                    "data": {
                        "message_id": message_id,
                        "channel_id": message["channel_id"]
                    }
                }
            )
            
            return {"message": "Message deleted successfully"}

    async def _verify_channel_access(
        self,
        db: aiosqlite.Connection,
        channel_id: int,
        user_id: int,
        require_membership: bool = True
    ) -> None:
        """Verify user has access to channel.
        
        Args:
            db: Database connection
            channel_id: Channel ID to check
            user_id: User ID to check
            require_membership: If True, verify user is a member regardless of channel type.
                              If False, only verify membership for non-public channels.
        """
        async with db.execute(
            "SELECT type FROM channels WHERE channel_id = ?",
            (channel_id,)
        ) as cursor:
            channel = await cursor.fetchone()
            if not channel:
                raise ValueError("Channel not found")
            
            # For non-public channels, always verify membership
            # For public channels, verify membership only if require_membership is True
            if channel["type"] != "public" or require_membership:
                async with db.execute(
                    """
                    SELECT 1 FROM channels_members
                    WHERE channel_id = ? AND user_id = ?
                    """,
                    (channel_id, user_id)
                ) as cursor:
                    if not await cursor.fetchone():
                        raise_forbidden("Not a member of this channel")

    async def _handle_reply_deletion(
        self,
        db: aiosqlite.Connection,
        cur: aiosqlite.Cursor,
        message: Dict[str, Any]
    ) -> None:
        """Handle deletion of a reply, including parent cleanup if needed."""
        # Check if parent is soft-deleted and this is the last reply
        await cur.execute(
            """
            SELECT content FROM messages 
            WHERE message_id = ? AND content = 'This message was deleted'
            """,
            (message["parent_id"],)
        )
        parent = await cur.fetchone()
        
        if parent:
            await cur.execute(
                """
                SELECT EXISTS(
                    SELECT 1 FROM messages 
                    WHERE parent_id = ? AND message_id != ?
                ) as has_other_replies
                """,
                (message["parent_id"], message["message_id"])
            )
            has_other_replies = (await cur.fetchone())["has_other_replies"]
            
            if not has_other_replies:
                # Clean up the entire thread
                await cur.execute(
                    """
                    DELETE FROM reactions WHERE message_id IN (
                        SELECT message_id FROM messages WHERE parent_id = ?
                    )
                    """,
                    (message["parent_id"],)
                )
                await cur.execute(
                    """
                    DELETE FROM attachments WHERE message_id IN (
                        SELECT message_id FROM messages WHERE parent_id = ?
                    )
                    """,
                    (message["parent_id"],)
                )
                await cur.execute(
                    "DELETE FROM messages WHERE parent_id = ?",
                    (message["parent_id"],)
                )
                
                # Clean up the parent
                await cur.execute(
                    "DELETE FROM reactions WHERE message_id = ?",
                    (message["parent_id"],)
                )
                await cur.execute(
                    "DELETE FROM attachments WHERE message_id = ?",
                    (message["parent_id"],)
                )
                await cur.execute(
                    "DELETE FROM messages WHERE message_id = ?",
                    (message["parent_id"],)
                )

message_service = MessageService() 