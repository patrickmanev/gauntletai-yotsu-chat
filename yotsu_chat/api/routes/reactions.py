from fastapi import APIRouter, Depends, HTTPException, Response
from ...core.auth import get_current_user
from ...core.database import get_db
from ...schemas.reaction import (
    ReactionCreate, 
    ReactionResponse, 
    MessageReactions,
    ReactionsList
)
from ...services.reaction_service import reaction_service
from ...utils.errors import YotsuError

import aiosqlite
from typing import List, Dict, Any

router = APIRouter(prefix="/reactions", tags=["reactions"])

@router.post("/messages/{message_id}", response_model=ReactionResponse, status_code=201)
async def add_reaction(
    message_id: int,
    reaction: ReactionCreate,
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db)
):
    """Add a reaction to a message."""
    try:
        # Validate emoji in schema
        reaction.validate_emoji()
        
        # Add reaction using service
        result = await reaction_service.add_reaction(
            db=db,
            message_id=message_id,
            emoji=reaction.emoji,
            user_id=current_user["user_id"]
        )
        
        return ReactionResponse(**result)
    except YotsuError as e:
        # Pass through YotsuErrors (including duplicate reactions) with their status codes
        raise e
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/messages/{message_id}")
async def remove_reaction(
    message_id: int,
    emoji: str,
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db)
):
    """Remove a reaction from a message."""
    try:
        await reaction_service.remove_reaction(
            db=db,
            message_id=message_id,
            emoji=emoji,
            user_id=current_user["user_id"]
        )
        return Response(status_code=204)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/messages", response_model=ReactionsList)
async def get_reactions(
    message_ids: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db)
):
    """List all reactions for multiple messages.
    
    Args:
        message_ids: Comma-separated list of message IDs
    
    Returns:
        ReactionsList containing reactions for each message
    """
    try:
        # Parse message IDs from comma-separated string
        message_id_list = [int(mid.strip()) for mid in message_ids.split(",")]
        raw_reactions = await reaction_service.list_reactions(
            db=db,
            message_ids=message_id_list,
            user_id=current_user["user_id"]
        )
        
        # Convert to ReactionsList format
        return ReactionsList(
            reactions={
                mid: MessageReactions(reactions=reactions)
                for mid, reactions in raw_reactions.items()
            }
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) 