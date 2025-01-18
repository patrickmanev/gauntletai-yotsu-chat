from fastapi import APIRouter, Depends, HTTPException, Query
import aiosqlite
from typing import List

from ...schemas.channel import (
    ChannelMember,
    ChannelMemberCreate, 
    AddMemberRequest,
    ChannelRole
)
from ...services.member_service import member_service
from ...services.role_service import role_service
from ...core.auth import get_current_user
from ...core.database import get_db
from ...utils import debug_log
from ...utils.errors import YotsuError

router = APIRouter(prefix="/members", tags=["members"])

@router.get("", response_model=List[ChannelMember])
async def list_channel_members(
    channel_ids: List[int] = Query(..., description="List of channel IDs to get members for"),
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db)
):
    """List members for multiple channels.
    
    For public channels:
    - Anyone can view the member list
    
    For private/DM/notes channels:
    - Only members can view the member list
    
    Args:
        channel_ids: List of channel IDs to get members for
        current_user: Current authenticated user
        db: Database connection
    
    Returns:
        List of channel members with their roles (if applicable), display names, and joined timestamps
    
    Raises:
        HTTPException: If any channel is not found or user lacks permission to view its members
    """
    try:
        members = await member_service.get_members(
            db=db,
            channel_ids=channel_ids,
            requesting_user_id=current_user["user_id"]
        )
        return members
    except (ValueError, YotsuError) as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/{channel_id}/members", status_code=201)
async def add_channel_member(
    channel_id: int,
    member: AddMemberRequest,
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db)
) -> List[dict]:
    """Add one or more members to a channel."""
    try:
        return await member_service.add_members(
            db=db,
            channel_id=channel_id,
            user_ids=member.user_ids,
            current_user_id=current_user["user_id"]
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except YotsuError:
        raise

@router.delete("/{channel_id}/{user_id}", status_code=204)
async def remove_channel_member(
    channel_id: int,
    user_id: int,
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db)
):
    """Remove a member from a channel."""
    try:
        await member_service.remove_member(
            db=db,
            channel_id=channel_id,
            target_user_id=user_id,
            current_user_id=current_user["user_id"]
        )
    except (ValueError, YotsuError) as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/{channel_id}/transfer")
async def transfer_channel_ownership(
    channel_id: int,
    new_owner: ChannelMemberCreate,
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db)
):
    """Transfer ownership of a private channel to another member."""
    try:    
        # Transfer ownership
        await role_service.transfer_ownership(
            db=db,
            channel_id=channel_id,
            new_owner_id=new_owner.user_id,
            current_owner_id=current_user["user_id"]
        )
        
        return {"message": "Channel ownership transferred successfully"}
        
    except HTTPException as e:
        # Re-raise HTTP exceptions from the service layer
        raise e
    except (ValueError, YotsuError) as e:
        # Handle validation errors not wrapped in HTTPException
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        debug_log("ERROR", f"Failed to transfer ownership: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to transfer ownership")

@router.put("/{channel_id}/{user_id}/promote")
async def promote_to_admin(
    channel_id: int,
    user_id: int,
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db)
):
    """Promote a member to admin in a private channel."""
    await role_service.update_member_role(
        db=db,
        channel_id=channel_id,
        user_id=user_id,
        new_role=ChannelRole.ADMIN,
        current_user_id=current_user["user_id"]
    )
    return {"message": "Member promoted to admin", "user_id": user_id}

@router.put("/{channel_id}/{user_id}/demote")
async def demote_to_member(
    channel_id: int,
    user_id: int,
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db)
):
    """Demote an admin to regular member in a private channel."""
    await role_service.update_member_role(
        db=db,
        channel_id=channel_id,
        user_id=user_id,
        new_role=ChannelRole.MEMBER,
        current_user_id=current_user["user_id"]
    )
    return {"message": "Admin demoted to member", "user_id": user_id} 