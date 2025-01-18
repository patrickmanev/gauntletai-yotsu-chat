from typing import Optional, List, Dict, Union
import logging
import aiosqlite
from fastapi import HTTPException

from ..utils import debug_log
from ..utils.errors import YotsuError, raise_forbidden
from ..schemas.channel import ChannelType, ChannelRole
from .member_service import member_service
from ..core.ws_core import manager as ws_manager
from ..core.ws_events import create_event, MessageData, MessageDeleteData

logger = logging.getLogger(__name__)

class MessageService:
    def __init__(self):
        debug_log("MESSAGE", "Initializing message service")
    
    async def send_message(
        self,
        db: aiosqlite.Connection,
        channel_id: int,
        user_id: int,
        content: str,
        reply_to: Optional[int] = None
    ) -> dict:
        """Send a message to a channel.
        
        Args:
            db: Database connection
            channel_id: Channel ID to send message to
            user_id: User ID sending the message
            content: Message content
            reply_to: Optional message ID being replied to
            
        Returns:
            Message info dict
            
        Raises:
            HTTPException: If user is not authorized to send messages
        """
        debug_log("MESSAGE", f"Sending message to channel {channel_id}")
        debug_log("MESSAGE", f"├─ User: {user_id}")
        debug_log("MESSAGE", f"├─ Content: {content}")
        if reply_to:
            debug_log("MESSAGE", f"├─ Reply to: {reply_to}")
        
        try:
            # Verify user is a member of the channel
            member_info = await member_service.get_member_info(db, channel_id, user_id)
            if not member_info:
                debug_log("MESSAGE", "└─ User is not a member")
                raise_forbidden("Not authorized to send messages to this channel")
            
            # Insert message
            async with db.execute(
                """
                INSERT INTO messages (channel_id, user_id, content, reply_to)
                VALUES (?, ?, ?, ?)
                RETURNING message_id
                """,
                (channel_id, user_id, content, reply_to)
            ) as cursor:
                message_id = (await cursor.fetchone())[0]
            
            # Get full message info
            message = await self.get_message(db, message_id)
            await db.commit()
            
            # Broadcast message.sent event
            event = create_event(
                "message.sent",
                MessageData(
                    message_id=message_id,
                    channel_id=channel_id,
                    user_id=user_id,
                    content=content,
                    reply_to=reply_to,
                    display_name=message["display_name"],
                    created_at=message["created_at"]
                )
            )
            await ws_manager.broadcast_to_subscribers(channel_id, event)
            debug_log("MESSAGE", f"└─ Broadcasted message.sent for message {message_id}")
            
            return message
            
        except YotsuError:
            raise
        except Exception as e:
            debug_log("ERROR", f"Failed to send message: {str(e)}")
            await db.rollback()
            raise HTTPException(status_code=500, detail="Failed to send message")
    
    async def get_message(
        self,
        db: aiosqlite.Connection,
        message_id: int
    ) -> Optional[dict]:
        """Get a single message by ID."""
        async with db.execute(
            """
            SELECT 
                m.message_id,
                m.channel_id,
                m.user_id,
                m.content,
                m.reply_to,
                m.created_at,
                u.display_name
            FROM messages m
            JOIN users u ON m.user_id = u.user_id
            WHERE m.message_id = ?
            """,
            [message_id]
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return None
            return dict(row)
    
    async def list_messages(
        self,
        db: aiosqlite.Connection,
        channel_id: int,
        user_id: int,
        before: Optional[int] = None,
        limit: int = 50
    ) -> List[dict]:
        """List messages in a channel with pagination.
        
        Args:
            db: Database connection
            channel_id: Channel ID to list messages for
            user_id: User ID requesting the messages
            before: Optional message ID to get messages before
            limit: Maximum number of messages to return
            
        Returns:
            List of message info dicts
            
        Raises:
            HTTPException: If user is not authorized to view messages
        """
        debug_log("MESSAGE", f"Listing messages for channel {channel_id}")
        debug_log("MESSAGE", f"├─ User: {user_id}")
        debug_log("MESSAGE", f"├─ Before: {before}")
        debug_log("MESSAGE", f"├─ Limit: {limit}")
        
        try:
            # Verify user is a member of the channel
            member_info = await member_service.get_member_info(db, channel_id, user_id)
            if not member_info:
                debug_log("MESSAGE", "└─ User is not a member")
                raise_forbidden("Not authorized to view messages in this channel")
            
            # Build query
            query = """
                SELECT 
                    m.message_id,
                    m.channel_id,
                    m.user_id,
                    m.content,
                    m.reply_to,
                    m.created_at,
                    u.display_name
                FROM messages m
                JOIN users u ON m.user_id = u.user_id
                WHERE m.channel_id = ?
            """
            params = [channel_id]
            
            if before:
                query += " AND m.message_id < ?"
                params.append(before)
            
            query += """
                ORDER BY m.message_id DESC
                LIMIT ?
            """
            params.append(limit)
            
            # Execute query
            async with db.execute(query, params) as cursor:
                columns = [col[0] for col in cursor.description]
                rows = await cursor.fetchall()
                messages = [dict(zip(columns, row)) for row in rows]
            
            debug_log("MESSAGE", f"└─ Found {len(messages)} messages")
            return messages
            
        except YotsuError:
            raise
        except Exception as e:
            debug_log("ERROR", f"Failed to list messages: {str(e)}")
            raise HTTPException(status_code=500, detail="Failed to list messages")
    
    async def delete_message(
        self,
        db: aiosqlite.Connection,
        message_id: int,
        user_id: int
    ) -> None:
        """Delete a message.
        
        Rules:
        - Users can delete their own messages
        - Channel owners/admins can delete any message
        - Thread parent messages are soft deleted (marked as deleted but kept in DB)
        - Regular messages are hard deleted
        """
        debug_log("MESSAGE", f"Deleting message {message_id}")
        debug_log("MESSAGE", f"├─ User: {user_id}")
        
        try:
            # Get message info first
            message = await self.get_message(db, message_id)
            if not message:
                debug_log("MESSAGE", "└─ Message not found")
                raise HTTPException(status_code=404, detail="Message not found")
            
            # Users can always delete their own messages
            if message["user_id"] != user_id:
                # For messages by others, check if user is owner/admin
                member_info = await member_service.get_member_info(
                    db, message["channel_id"], user_id
                )
                if not member_info:
                    debug_log("MESSAGE", "└─ User is not a member")
                    raise_forbidden("Not authorized to delete messages in this channel")
                
                if member_info["role"] not in [ChannelRole.OWNER, ChannelRole.ADMIN]:
                    debug_log("MESSAGE", "└─ User lacks required role")
                    raise_forbidden("Only owners and admins can delete other users' messages")
            
            # Check if message has replies (is a thread parent)
            async with db.execute(
                "SELECT 1 FROM messages WHERE parent_id = ?",
                [message_id]
            ) as cursor:
                has_replies = bool(await cursor.fetchone())
            
            if has_replies:
                debug_log("MESSAGE", "├─ Message has replies, performing soft delete")
                # Soft delete - mark as deleted but keep in DB
                await db.execute(
                    """
                    UPDATE messages 
                    SET is_deleted = TRUE, content = '[deleted]'
                    WHERE message_id = ?
                    """,
                    [message_id]
                )
            else:
                debug_log("MESSAGE", "├─ Message has no replies, performing hard delete")
                # Hard delete - remove from DB
                await db.execute(
                    "DELETE FROM messages WHERE message_id = ?",
                    [message_id]
                )
            
            await db.commit()
            
            # Broadcast message.deleted event
            event = create_event(
                "message.deleted",
                MessageDeleteData(
                    message_id=message_id,
                    channel_id=message["channel_id"]
                )
            )
            await ws_manager.broadcast_to_subscribers(message["channel_id"], event)
            debug_log("MESSAGE", f"└─ Broadcasted message.deleted for message {message_id}")
            
        except YotsuError:
            raise
        except Exception as e:
            debug_log("ERROR", f"Failed to delete message: {str(e)}")
            await db.rollback()
            raise HTTPException(status_code=500, detail="Failed to delete message")

# Global instance
message_service = MessageService() 