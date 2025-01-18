from fastapi import APIRouter, Depends, HTTPException, Query, Response
from yotsu_chat.core.auth import get_current_user
from yotsu_chat.schemas.channel import (
    ChannelCreate, ChannelResponse, ChannelType, ChannelUpdate, PublicChannelListResponse
)
from yotsu_chat.core.database import get_db
from yotsu_chat.services.channel_service import channel_service
from yotsu_chat.utils import debug_log
from typing import List, Optional
import aiosqlite


router = APIRouter(prefix="/channels", tags=["channels"])

# Channel CRUD operations
@router.post("", response_model=ChannelResponse, status_code=201)
async def create_channel(
    channel: ChannelCreate,
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db)
):
    """Create a new channel."""
    try:
        channel_info = await channel_service.create_channel(
            db=db,
            name=channel.name,
            channel_type=channel.type,
            created_by=current_user["user_id"],
            initial_members=channel.initial_members
        )
        return ChannelResponse(**channel_info)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.get("", response_model=List[ChannelResponse])
async def list_channels(
    types: Optional[List[str]] = Query(None, description="Channel types to include"),
    limit: Optional[int] = None,
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db)
):
    """List channels the user is a member of."""
    try:
        # Convert string types to ChannelType enums
        enum_types = [ChannelType(t) for t in types] if types else None
        
        channels = await channel_service.list_channels(
            db=db,
            user_id=current_user["user_id"],
            include_types=enum_types,
            limit=limit
        )
        return [ChannelResponse(**ch) for ch in channels]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/public", response_model=List[PublicChannelListResponse])
async def list_public_channels(
    search: Optional[str] = None,
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db)
) -> List[PublicChannelListResponse]:
    """List all public channels with optional search. Returns minimal info for channel selection UI."""
    debug_log("API", f"Listing public channels, search={search}")
    
    try:
        channels = await channel_service.list_public_channels(
            db,
            search=search
        )
        
        debug_log("API", f"└─ Found {len(channels)} channels")
        return [PublicChannelListResponse(**ch) for ch in channels]
        
    except Exception as e:
        debug_log("ERROR", f"Failed to list public channels: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/{channel_id}", response_model=ChannelResponse)
async def update_channel(
    channel_id: int,
    channel_update: ChannelUpdate,
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db)
):
    """Update channel name. Only private channel owners can update the name."""
    try:
        updated = await channel_service.update_channel(
            db=db,
            channel_id=channel_id,
            name=channel_update.name,
            current_user_id=current_user["user_id"]
        )
        return ChannelResponse(**updated)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) 