from fastapi import APIRouter, Depends, HTTPException
from yotsu_chat.core.auth import get_current_user
from yotsu_chat.schemas.reaction import ReactionCreate, ReactionResponse, ReactionCount
from yotsu_chat.core.database import get_db
from yotsu_chat.core.ws_core import manager as ws_manager
from typing import List
import aiosqlite
import json

router = APIRouter(prefix="/reactions", tags=["reactions"])

@router.post("/messages/{message_id}", response_model=ReactionResponse, status_code=201)
async def add_reaction(
    message_id: int,
    reaction: ReactionCreate,
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db)
):
    # Validate emoji
    reaction.validate_emoji()
    
    # Check if message exists and get channel_id
    async with db.execute(
        "SELECT channel_id FROM messages WHERE message_id = ?",
        (message_id,)
    ) as cursor:
        message = await cursor.fetchone()
        if not message:
            raise HTTPException(status_code=404, detail="Message not found")
        channel_id = message["channel_id"]
    
    # Count unique emojis for this message
    async with db.execute(
        "SELECT COUNT(DISTINCT emoji) FROM reactions WHERE message_id = ?",
        (message_id,)
    ) as cursor:
        unique_emoji_count = (await cursor.fetchone())[0]
        
    # Check if this would exceed the emoji limit
    async with db.execute(
        "SELECT 1 FROM reactions WHERE message_id = ? AND emoji = ?",
        (message_id, reaction.emoji)
    ) as cursor:
        existing_reaction = await cursor.fetchone()
        if not existing_reaction and unique_emoji_count >= 12:
            raise HTTPException(
                status_code=400,
                detail="Maximum number of unique emoji reactions (12) reached for this message"
            )
    
    try:
        await db.execute(
            """
            INSERT INTO reactions (message_id, emoji, user_id)
            VALUES (?, ?, ?)
            """,
            (message_id, reaction.emoji, current_user["user_id"])
        )
        await db.commit()
    except aiosqlite.IntegrityError:
        raise HTTPException(
            status_code=400,
            detail="You have already reacted with this emoji"
        )
    
    response = ReactionResponse(
        message_id=message_id,
        emoji=reaction.emoji,
        user_id=current_user["user_id"],
        created_at=str(await db.execute_fetchall("SELECT datetime('now')"))[0]
    )
    
    # Broadcast reaction added to channel
    event = {
        "type": "reaction.added",
        "data": {
            "message_id": message_id,
            "channel_id": channel_id,
            "user_id": current_user["user_id"],
            "emoji": reaction.emoji,
            "created_at": response.created_at
        }
    }
    await ws_manager.broadcast_to_channel(channel_id, event)
    
    return response

@router.delete("/messages/{message_id}/{emoji}")
async def remove_reaction(
    message_id: int,
    emoji: str,
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db)
):
    # Get channel_id first
    async with db.execute(
        "SELECT channel_id FROM messages WHERE message_id = ?",
        (message_id,)
    ) as cursor:
        message = await cursor.fetchone()
        if not message:
            raise HTTPException(status_code=404, detail="Message not found")
        channel_id = message["channel_id"]
    
    result = await db.execute(
        """
        DELETE FROM reactions
        WHERE message_id = ? AND emoji = ? AND user_id = ?
        """,
        (message_id, emoji, current_user["user_id"])
    )
    await db.commit()
    
    if result.rowcount == 0:
        raise HTTPException(
            status_code=404,
            detail="Reaction not found"
        )
    
    # Broadcast reaction removed to channel
    event = {
        "type": "reaction.removed",
        "data": {
            "message_id": message_id,
            "channel_id": channel_id,
            "user_id": current_user["user_id"],
            "emoji": emoji
        }
    }
    await ws_manager.broadcast_to_channel(channel_id, event)
    
    return {"status": "success"}

@router.get("/messages/{message_id}", response_model=List[ReactionCount])
async def get_reactions(
    message_id: int,
    db: aiosqlite.Connection = Depends(get_db)
):
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
    
    return [
        ReactionCount(
            emoji=row[0],
            count=row[1],
            users=[int(uid) for uid in str(row[2]).split(",")]
        )
        for row in reactions
    ] 