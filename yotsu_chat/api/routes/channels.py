from fastapi import APIRouter, Depends, HTTPException, Query, Response
from yotsu_chat.core.auth import get_current_user
from yotsu_chat.schemas.channel import (
    ChannelCreate, ChannelResponse, ChannelType, ChannelUpdate
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
        channel_id = await channel_service.create_channel(
            db=db,
            name=channel.name,
            type=channel.type,
            created_by=current_user["user_id"],
            initial_members=channel.initial_members
        )
        
        # Get created channel details
        channels = await channel_service.list_channels(
            db=db,
            user_id=current_user["user_id"],
            include_types=[channel.type]
        )
        
        for ch in channels:
            if ch["channel_id"] == channel_id:
                return ChannelResponse(**ch)
        
        raise HTTPException(status_code=500, detail="Channel creation failed")
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

@router.get("/public", response_model=List[ChannelResponse])
async def list_public_channels(
    search: Optional[str] = None,
    offset: Optional[int] = Query(default=0, ge=0),
    limit: Optional[int] = Query(default=50, ge=1, le=100),
    response: Response = None,
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db)
) -> List[ChannelResponse]:
    """List all public channels with optional search and pagination."""
    debug_log("API", f"Listing public channels, search={search}, offset={offset}, limit={limit}")
    debug_log("API", f"├─ Current user: {current_user['user_id']}")
    
    try:
        channels, total_count = await channel_service.list_public_channels(
            db,
            current_user["user_id"],
            search=search,
            offset=offset,
            limit=limit
        )
        
        debug_log("API", f"├─ Found {len(channels)} channels")
        debug_log("API", f"├─ Total count: {total_count}")
        
        if response:
            response.headers["X-Total-Count"] = str(total_count)
        
        channel_responses = [ChannelResponse(**ch) for ch in channels]
        debug_log("API", f"└─ Converted to response models")
        return channel_responses
        
    except Exception as e:
        debug_log("ERROR", f"Failed to list public channels: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{channel_id}", response_model=ChannelResponse)
async def get_channel(
    channel_id: int,
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db)
):
    """Get channel details."""
    try:
        # First check if channel exists and get its type
        async with db.execute(
            "SELECT type FROM channels WHERE channel_id = ?",
            [channel_id]
        ) as cursor:
            channel = await cursor.fetchone()
            if not channel:
                raise HTTPException(status_code=404, detail="Channel not found")
            
            channel_type = channel[0]
            
            # For private channels, verify membership
            if channel_type == ChannelType.PRIVATE:
                async with db.execute(
                    """SELECT 1 FROM channels_members 
                    WHERE channel_id = ? AND user_id = ?""",
                    [channel_id, current_user["user_id"]]
                ) as cursor:
                    if not await cursor.fetchone():
                        raise HTTPException(status_code=404, detail="Channel not found")
        
        # Get full channel details
        channels = await channel_service.list_channels(
            db=db,
            user_id=current_user["user_id"]
        )
        
        for channel in channels:
            if channel["channel_id"] == channel_id:
                return ChannelResponse(**channel)
        
        raise HTTPException(status_code=404, detail="Channel not found")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) 

@router.patch("/{channel_id}", response_model=ChannelResponse)
async def update_channel(
    channel_id: int,
    channel_update_data: dict,  # Change to dict to prevent premature validation
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db)
):
    """Update channel name."""
    debug_log("API", f"Updating channel {channel_id}")
    debug_log("API", f"├─ New name: {channel_update_data.get('name')}")
    
    try:
        # Get channel type first for validation
        async with db.execute(
            "SELECT type FROM channels WHERE channel_id = ?",
            [channel_id]
        ) as cursor:
            result = await cursor.fetchone()
            if not result:
                raise HTTPException(status_code=404, detail="Channel not found")
            
            # Set channel type before validation
            channel_update_data["channel_type"] = result[0]
            
            # Now validate the model
            channel = ChannelUpdate(**channel_update_data)
        
        updated = await channel_service.update_channel(
            db=db,
            channel_id=channel_id,
            name=channel.name,
            current_user_id=current_user["user_id"]
        )
        
        debug_log("API", "└─ Channel updated successfully")
        return ChannelResponse(**updated)
        
    except ValueError as e:
        debug_log("API", f"Validation error: {str(e)}")
        raise HTTPException(status_code=422, detail=[{"msg": str(e)}])
    except HTTPException as e:
        debug_log("API", f"HTTP error: {e.status_code} - {e.detail}")
        if e.status_code == 422:
            # Ensure consistent format for 422 errors
            if isinstance(e.detail, list):
                raise e
            raise HTTPException(status_code=422, detail=[{"msg": str(e.detail)}])
        raise e
    except Exception as e:
        debug_log("ERROR", f"Failed to update channel: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e)) 