from typing import List, Dict, Any
import aiosqlite
import logging

from ..core.ws_core import manager as ws_manager
from ..core.ws_events import create_event, ReactionData
from ..core.config import get_settings
from ..utils import debug_log
from ..services.message_service import message_service
from ..services.channel_service import channel_service
from ..utils.errors import YotsuError, ErrorCode, raise_forbidden

logger = logging.getLogger(__name__)
settings = get_settings()

class ReactionService:
    async def add_reaction(
        self,
        db: aiosqlite.Connection,
        message_id: int,
        emoji: str,
        user_id: int
    ) -> Dict[str, Any]:
        """Add a reaction to a message.
        
        Raises:
            ValueError: If message not found or emoji limit reached
            YotsuError: If user cannot access the channel or duplicate reaction
        """
        debug_log("REACTION", f"Adding reaction {emoji} to message {message_id} by user {user_id}")
        
        # Get message info and check existing reactions in one query
        async with db.execute(
            """
            SELECT 
                m.channel_id,
                (SELECT COUNT(DISTINCT emoji) FROM reactions WHERE message_id = ?) as unique_emoji_count,
                EXISTS(
                    SELECT 1 FROM reactions 
                    WHERE message_id = ? AND emoji = ? AND user_id = ?
                ) as has_existing_reaction
            FROM messages m
            WHERE m.message_id = ?
            """,
            (message_id, message_id, emoji, user_id, message_id)
        ) as cursor:
            result = await cursor.fetchone()
            if not result:
                debug_log("REACTION", f"Message {message_id} not found")
                raise ValueError("Message not found")
            
            channel_id = result["channel_id"]
            unique_emoji_count = result["unique_emoji_count"]
            has_existing_reaction = result["has_existing_reaction"]
            
            debug_log("REACTION", f"Message {message_id} belongs to channel {channel_id}")
            debug_log("REACTION", f"Message has {unique_emoji_count} unique reactions")
        
        # Verify channel access
        await message_service._verify_channel_access(db, channel_id, user_id)
        
        # Check for duplicate reaction - return early with soft error
        if has_existing_reaction:
            debug_log("REACTION", f"User {user_id} already reacted with {emoji} to message {message_id}")
            raise YotsuError(
                status_code=409,  # Conflict
                error_code=ErrorCode.DUPLICATE_REACTION,
                message="Already reacted with this emoji",
                details={
                    "message_id": message_id,
                    "emoji": emoji,
                    "user_id": user_id
                }
            )
        
        # Check emoji limit
        if unique_emoji_count >= settings.reaction.max_unique_emojis:
            debug_log("REACTION", f"Message {message_id} has reached max unique reactions ({settings.reaction.max_unique_emojis})")
            raise ValueError(
                f"Maximum number of unique emoji reactions ({settings.reaction.max_unique_emojis}) reached for this message"
            )
        
        # Add reaction
        await db.execute(
            """
            INSERT INTO reactions (message_id, emoji, user_id)
            VALUES (?, ?, ?)
            """,
            (message_id, emoji, user_id)
        )
        await db.commit()
        debug_log("REACTION", f"Added reaction {emoji} to message {message_id} by user {user_id}")
        
        # Prepare response data
        response_data = ReactionData(
            message_id=message_id,
            emoji=emoji,
            user_id=user_id
        )
        
        # Broadcast reaction added to channel
        event = create_event("reaction.added", response_data)
        await ws_manager.broadcast_to_subscribers(channel_id, event)
        debug_log("REACTION", f"Broadcasted reaction.added event for message {message_id}")
        
        return response_data.model_dump()

    async def remove_reaction(
        self,
        db: aiosqlite.Connection,
        message_id: int,
        emoji: str,
        user_id: int
    ) -> None:
        """Remove a specific emoji reaction from a message."""
        try:
            # Get the channel_id for broadcasting
            cursor = await db.execute(
                """SELECT channel_id FROM messages WHERE message_id = ?""",
                (message_id,)
            )
            result = await cursor.fetchone()
            if not result:
                raise ValueError("Message not found")
            channel_id = result[0]

            # Delete the specific reaction
            await db.execute(
                """DELETE FROM reactions 
                WHERE message_id = ? AND user_id = ? AND emoji = ?""",
                (message_id, user_id, emoji)
            )
            await db.commit()

            # Broadcast the reaction.removed event
            event_data = ReactionData(
                message_id=message_id,
                user_id=user_id,
                emoji=emoji
            )
            event = create_event("reaction.removed", event_data)
            await ws_manager.broadcast_to_subscribers(channel_id, event)
        except ValueError as e:
            debug_log("REACTION", f"Error removing reaction: {e}")
            raise e

    async def list_reactions(
        self,
        db: aiosqlite.Connection,
        message_ids: List[int],
        user_id: int
    ) -> Dict[int, Dict[str, List[int]]]:
        """List all reactions for multiple messages.
        
        Raises:
            YotsuError: If any message is from a channel the user cannot access
        
        Returns:
            Dict mapping message_id to a dict of emoji -> list of user_ids
        """
        debug_log("REACTION", f"Listing reactions for messages: {message_ids}")
        
        if not message_ids:
            return {}

        # Get channel IDs for all messages
        async with db.execute(
            f"""
            SELECT message_id, channel_id 
            FROM messages 
            WHERE message_id IN ({','.join('?' * len(message_ids))})
            """,
            message_ids
        ) as cursor:
            message_channels = {row["message_id"]: row["channel_id"] 
                              async for row in cursor}
            
        # Verify all messages exist
        if len(message_channels) != len(message_ids):
            raise ValueError("One or more messages not found")

        # Get all channels user has access to
        accessible_channels = await channel_service.list_channels(db, user_id)
        accessible_channel_ids = {channel["channel_id"] for channel in accessible_channels}

        # Verify user has access to all channels
        for channel_id in message_channels.values():
            if channel_id not in accessible_channel_ids:
                raise_forbidden("Not authorized to view one or more messages")

        # Get reactions for all messages
        async with db.execute(
            f"""
            SELECT message_id, emoji, user_id
            FROM reactions
            WHERE message_id IN ({','.join('?' * len(message_ids))})
            ORDER BY message_id, emoji
            """,
            message_ids
        ) as cursor:
            # Initialize result structure
            result: Dict[int, Dict[str, List[int]]] = {
                mid: {} for mid in message_ids
            }
            
            # Build the response structure
            async for row in cursor:
                mid, emoji, uid = row["message_id"], row["emoji"], row["user_id"]
                if emoji not in result[mid]:
                    result[mid][emoji] = []
                result[mid][emoji].append(uid)
        
        return result

reaction_service = ReactionService() 