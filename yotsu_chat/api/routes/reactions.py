from fastapi import APIRouter, Depends, HTTPException
from ...core.auth import get_current_user
from ...core.database import get_db
from ...schemas.reaction import ReactionCreate, ReactionResponse, ReactionCount
from ...services.reaction_service import reaction_service
from ...utils import debug_log

import aiosqlite
from typing import List
import logging

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
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/messages/{message_id}/{emoji}")
async def remove_reaction(
    message_id: int,
    emoji: str,
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db)
):
    """Remove a reaction from a message."""
    try:
        result = await reaction_service.remove_reaction(
            db=db,
            message_id=message_id,
            emoji=emoji,
            user_id=current_user["user_id"]
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("/messages/{message_id}", response_model=List[ReactionCount])
async def get_reactions(
    message_id: int,
    db: aiosqlite.Connection = Depends(get_db)
):
    """List all reactions for a message."""
    try:
        reactions = await reaction_service.list_reactions(
            db=db,
            message_id=message_id
        )
        return [ReactionCount(**reaction) for reaction in reactions]
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) 