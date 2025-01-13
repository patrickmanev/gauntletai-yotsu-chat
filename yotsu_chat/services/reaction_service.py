from typing import List, Dict, Any
import aiosqlite
import logging
from datetime import datetime

from ..core.ws_core import manager as ws_manager
from ..core.config import get_settings
from ..utils import debug_log
from ..utils.errors import raise_unauthorized, raise_forbidden
from ..services.message_service import message_service

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
        """Add a reaction to a message."""
        debug_log("REACTION", f"Adding reaction {emoji} to message {message_id} by user {user_id}")
        
        # Get message and channel info
        async with db.execute(
            "SELECT channel_id FROM messages WHERE message_id = ?",
            (message_id,)
        ) as cursor:
            message = await cursor.fetchone()
            if not message:
                debug_log("REACTION", f"Message {message_id} not found")
                raise ValueError("Message not found")
            channel_id = message["channel_id"]
            debug_log("REACTION", f"Message {message_id} belongs to channel {channel_id}")
        
        # Verify channel access
        await message_service._verify_channel_access(db, channel_id, user_id)
        
        # Count unique emojis for this message
        async with db.execute(
            "SELECT COUNT(DISTINCT emoji) FROM reactions WHERE message_id = ?",
            (message_id,)
        ) as cursor:
            unique_emoji_count = (await cursor.fetchone())[0]
            debug_log("REACTION", f"Message {message_id} has {unique_emoji_count} unique reactions")
        
        # Check if this would exceed the emoji limit
        async with db.execute(
            "SELECT 1 FROM reactions WHERE message_id = ? AND emoji = ?",
            (message_id, emoji)
        ) as cursor:
            existing_reaction = await cursor.fetchone()
            if not existing_reaction and unique_emoji_count >= settings.reaction.max_unique_emojis:
                debug_log("REACTION", f"Message {message_id} has reached max unique reactions ({settings.reaction.max_unique_emojis})")
                raise ValueError(
                    f"Maximum number of unique emoji reactions ({settings.reaction.max_unique_emojis}) reached for this message"
                )
        
        try:
            await db.execute(
                """
                INSERT INTO reactions (message_id, emoji, user_id)
                VALUES (?, ?, ?)
                """,
                (message_id, emoji, user_id)
            )
            await db.commit()
            debug_log("REACTION", f"Added reaction {emoji} to message {message_id} by user {user_id}")
        except aiosqlite.IntegrityError:
            debug_log("REACTION", f"User {user_id} already reacted with {emoji} to message {message_id}")
            raise ValueError("You have already reacted with this emoji")
        
        # Get creation timestamp
        async with db.execute("SELECT datetime('now')") as cursor:
            created_at = (await cursor.fetchone())[0]
        
        # Prepare response data
        response_data = {
            "message_id": message_id,
            "emoji": emoji,
            "user_id": user_id,
            "created_at": created_at
        }
        
        # Broadcast reaction added to channel
        event = {
            "type": "reaction.added",
            "data": {
                **response_data,
                "channel_id": channel_id
            }
        }
        await ws_manager.broadcast_to_subscribers(channel_id, event)
        debug_log("REACTION", f"Broadcasted reaction.added event for message {message_id}")
        
        return response_data

    async def remove_reaction(
        self,
        db: aiosqlite.Connection,
        message_id: int,
        user_id: int
    ) -> None:
        """Remove a reaction from a message."""
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

            # Delete the reaction
            await db.execute(
                """DELETE FROM reactions 
                WHERE message_id = ? AND user_id = ?""",
                (message_id, user_id)
            )
            await db.commit()

            # Broadcast the reaction.removed event
            event = {
                "type": "reaction.removed",
                "data": {
                    "message_id": message_id,
                    "user_id": user_id,
                    "channel_id": channel_id
                }
            }
            await ws_manager.broadcast_to_subscribers(channel_id, event)
        except ValueError as e:
            debug_log("REACTION", f"Error removing reaction: {e}")
            raise e

    async def list_reactions(
        self,
        db: aiosqlite.Connection,
        message_id: int
    ) -> List[Dict[str, Any]]:
        """List all reactions for a message."""
        debug_log("REACTION", f"Listing reactions for message {message_id}")
        
        async with db.execute(
            """
            SELECT emoji, COUNT(*) as count, GROUP_CONCAT(user_id) as users
            FROM reactions
            WHERE message_id = ?
            GROUP BY emoji
            """,
            (message_id,)
        ) as cursor:
            reactions = await cursor.fetchall()
            debug_log("REACTION", f"Found {len(reactions)} unique reactions for message {message_id}")
        
        return [
            {
                "emoji": row[0],
                "count": row[1],
                "users": [int(uid) for uid in str(row[2]).split(",")]
            }
            for row in reactions
        ]

reaction_service = ReactionService() 