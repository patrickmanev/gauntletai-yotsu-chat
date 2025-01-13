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
        
        # If this is a reply, send thread update first
        if parent_id:
            # Get thread metadata
            async with db.execute(
                """
                SELECT 
                    COUNT(*) as reply_count,
                    MAX(message_id) as latest_reply_id
                FROM messages 
                WHERE parent_id = ?
                """,
                (parent_id,)
            ) as cursor:
                thread_meta = await cursor.fetchone()

            # Get latest reply details
            latest_reply = await self.get_message(db, thread_meta["latest_reply_id"], user_id)

            # Broadcast thread update first
            await ws_manager.broadcast_to_subscribers(
                channel_id,
                {
                    "type": "thread.update",
                    "data": {
                        "thread_id": parent_id,
                        "channel_id": channel_id,
                        "reply_count": thread_meta["reply_count"],
                        "latest_reply": {
                            "message_id": latest_reply["message_id"],
                            "content": latest_reply["content"],
                            "user_id": latest_reply["user_id"],
                            "display_name": latest_reply["display_name"],
                            "created_at": latest_reply["created_at"].isoformat()
                        }
                    }
                }
            )
            debug_log("MSG", f"Sent thread.update for thread {parent_id} - clients should wait for message.created")
        
        # Then broadcast the message creation
        await ws_manager.broadcast_to_subscribers(
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
        
        if parent_id:
            debug_log("MSG", f"Sent message.created for reply {message_id} in thread {parent_id} - clients can now render both updates")
        else:
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
        await ws_manager.broadcast_to_subscribers(
            updated_message["channel_id"],
            {
                "type": "message.updated",
                "data": {
                    "message_id": message_id,
                    "channel_id": updated_message["channel_id"],
                    "content": content,
                    "user_id": user_id,
                    "parent_id": updated_message["parent_id"],
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
    ) -> None:
        """Delete a message with proper cascade handling for threads."""
        debug_log("MSG", f"Starting deletion of message {message_id} by user {user_id}")
        
        async with db.cursor() as cur:
            # Get message and verify permissions
            message = await self.get_message(db, message_id, user_id)
            debug_log("MSG", f"Message details - channel: {message['channel_id']}, parent: {message['parent_id']}, author: {message['user_id']}")
            
            # Check if user is author or channel admin/owner
            if message["user_id"] != user_id:
                debug_log("MSG", f"Non-author deletion attempt - checking permissions")
                # Get channel type
                async with db.execute(
                    """
                    SELECT type FROM channels
                    WHERE channel_id = ?
                    """,
                    (message["channel_id"],)
                ) as cursor:
                    channel = await cursor.fetchone()
                    debug_log("MSG", f"Channel type: {channel['type']}")
                    
                # For public channels, only the author can delete
                if channel["type"] == "public":
                    debug_log("MSG", "Rejecting deletion - public channel requires author")
                    raise ValueError("In public channels, only the message author can delete their messages")
                    
                # For private channels, check if user is owner/admin
                await cur.execute(
                    """
                    SELECT role FROM channels_members
                    WHERE channel_id = ? AND user_id = ?
                    """,
                    (message["channel_id"], user_id)
                )
                member = await cur.fetchone()
                if not member or member["role"] not in ["owner", "admin"]:
                    debug_log("MSG", f"Rejecting deletion - user role: {member['role'] if member else 'none'}")
                    raise ValueError("No permission to delete this message")
            
            # Handle thread parent deletion
            if message["parent_id"] is None:
                debug_log("MSG", f"Processing parent message deletion - checking for replies")
                await cur.execute(
                    """
                    SELECT EXISTS(
                        SELECT 1 FROM messages WHERE parent_id = ?
                    ) as has_replies
                    """,
                    (message_id,)
                )
                has_replies = (await cur.fetchone())["has_replies"]
                debug_log("MSG", f"Parent message has replies: {has_replies}")
                
                if has_replies:
                    debug_log("MSG", "Soft deleting parent message with replies")
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
                    
                    debug_log("MSG", f"Broadcasting soft delete event for parent {message_id}")
                    await ws_manager.broadcast_to_subscribers(
                        message["channel_id"],
                        {
                            "type": "message.soft_deleted",
                            "data": {
                                "message_id": message_id,
                                "channel_id": message["channel_id"]
                            }
                        }
                    )
                    return None
            
            debug_log("MSG", f"Deleting message {message_id} attachments and reactions")
            # Delete message attachments and reactions
            await cur.execute("DELETE FROM reactions WHERE message_id = ?", (message_id,))
            await cur.execute("DELETE FROM attachments WHERE message_id = ?", (message_id,))
            
            # Delete the message
            await cur.execute("DELETE FROM messages WHERE message_id = ?", (message_id,))
            
            # For replies, check parent cleanup before committing
            parent_to_delete = None
            if message["parent_id"]:
                debug_log("MSG", "Checking if parent needs cleanup before commit")
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
                        debug_log("MSG", f"No other replies - cleaning up parent {message['parent_id']}")
                        # Clean up the parent in the same transaction
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
                        parent_to_delete = message["parent_id"]

            # Commit all changes in a single transaction
            await db.commit()
            debug_log("MSG", f"All database operations committed")
            
            # Now broadcast events
            if parent_to_delete:
                # If we're deleting a thread (parent + last reply), only broadcast parent deletion
                debug_log("MSG", f"Broadcasting deletion event for parent {parent_to_delete}")
                await ws_manager.broadcast_to_subscribers(
                    message["channel_id"],
                    {
                        "type": "message.deleted",
                        "data": {
                            "message_id": parent_to_delete,
                            "channel_id": message["channel_id"],
                            "parent_id": None
                        }
                    }
                )
            elif not message["parent_id"]:
                # If we're deleting a standalone message (not a reply), broadcast its deletion
                debug_log("MSG", f"Broadcasting deletion event for standalone message {message_id}")
                await ws_manager.broadcast_to_subscribers(
                    message["channel_id"],
                    {
                        "type": "message.deleted",
                        "data": {
                            "message_id": message_id,
                            "channel_id": message["channel_id"],
                            "parent_id": message["parent_id"]
                        }
                    }
                )
            else:
                # If we're deleting a reply (but not the last one), broadcast its deletion
                debug_log("MSG", f"Broadcasting deletion event for reply {message_id}")
                await ws_manager.broadcast_to_subscribers(
                    message["channel_id"],
                    {
                        "type": "message.deleted",
                        "data": {
                            "message_id": message_id,
                            "channel_id": message["channel_id"],
                            "parent_id": message["parent_id"]
                        }
                    }
                )
            
            return None

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
        debug_log("MSG", f"Checking parent {message['parent_id']} status after reply {message['message_id']} deletion")
        
        # Check if parent is soft-deleted and this is the last reply
        await cur.execute(
            """
            SELECT content FROM messages 
            WHERE message_id = ? AND content = 'This message was deleted'
            """,
            (message["parent_id"],)
        )
        parent = await cur.fetchone()
        debug_log("MSG", f"Parent is soft-deleted: {parent is not None}")
        
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
            debug_log("MSG", f"Parent has other replies: {has_other_replies}")
            
            if not has_other_replies:
                debug_log("MSG", f"No other replies - cleaning up parent {message['parent_id']}")
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
                await db.commit()
                debug_log("MSG", f"Parent {message['parent_id']} deleted from database")
                
                # Broadcast parent deletion after all cleanup
                debug_log("MSG", f"Broadcasting deletion event for parent {message['parent_id']}")
                await ws_manager.broadcast_to_subscribers(
                    message["channel_id"],
                    {
                        "type": "message.deleted",
                        "data": {
                            "message_id": message["parent_id"],
                            "channel_id": message["channel_id"],
                            "parent_id": None
                        }
                    }
                )

message_service = MessageService() 