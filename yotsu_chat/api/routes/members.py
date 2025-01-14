from fastapi import APIRouter, Depends, HTTPException
import aiosqlite
from typing import List

from ...schemas.channel import ChannelMember, ChannelMemberCreate, ChannelMemberUpdate, ChannelType, ChannelRole
from ...services.channel_service import channel_service
from ...services.role_service import role_service
from ...core.auth import get_current_user
from ...core.database import get_db
from ...utils import debug_log
from ...utils.errors import YotsuError

router = APIRouter(prefix="/members", tags=["members"])

@router.get("/{channel_id}", response_model=List[ChannelMember])
async def list_channel_members(
    channel_id: int,
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db)
):
    """List all members of a channel.
    
    For public channels:
    - Anyone can view the member list
    
    For private channels:
    - Only members can view the member list
    """
    try:
        # Get channel type first
        channel_type = await channel_service.verify_channel_type(db, channel_id)
        
        # For private channels, verify membership
        if channel_type == ChannelType.PRIVATE:
            is_member = await channel_service.is_channel_member(db, channel_id, current_user["user_id"])
            if not is_member:
                raise HTTPException(status_code=404, detail="Channel not found")
        
        # Get member list
        members = await channel_service.get_channel_members(db, channel_id)
        
        # Add channel_type to each member
        for member in members:
            member["channel_type"] = channel_type
            
        return members
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        debug_log("ERROR", f"Failed to list channel members: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to list channel members")

@router.post("/{channel_id}", response_model=ChannelMember, status_code=201)
async def add_channel_member(
    channel_id: int,
    member: ChannelMemberCreate,
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db)
):
    """Add a member to a channel.
    
    For public channels:
    - Any member can add new members
    
    For private channels:
    - Only owners and admins can add members
    """
    try:
        # Add the member
        await channel_service.add_member(
            db, 
            channel_id, 
            member.user_id,
            current_user["user_id"]
        )
        
        # Get the member info
        member_info = await channel_service.get_member_info(db, channel_id, member.user_id)
        if not member_info:
            raise HTTPException(status_code=500, detail="Failed to retrieve member info")
            
        return member_info
    except YotsuError as e:
        raise HTTPException(status_code=e.status_code, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        debug_log("ERROR", f"Failed to add channel member: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to add channel member")

@router.delete("/{channel_id}/{user_id}", status_code=204)
async def remove_channel_member(
    channel_id: int,
    user_id: int,
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db)
):
    """Remove a member from a channel.
    
    For public channels:
    - Members can only remove themselves (leave)
    
    For private channels:
    - Owners can remove anyone except themselves
    - Admins can remove regular members
    - Regular members can only remove themselves
    """
    try:
        await channel_service.remove_member(db, channel_id, user_id, current_user["user_id"])
        return None
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        debug_log("ERROR", f"Failed to remove channel member: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to remove channel member")

@router.put("/{channel_id}/{user_id}/role")
async def update_member_role(
    channel_id: int,
    user_id: int,
    role_update: ChannelMemberUpdate,
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db)
):
    """Update a member's role in a channel.
    
    Only applicable to private channels:
    - Owners can change any role except their own
    - Admins can manage regular members
    - Regular members cannot modify roles
    """
    try:
        # Get channel type first
        channel_type = await channel_service.verify_channel_type(db, channel_id)
        if channel_type != ChannelType.PRIVATE:
            raise HTTPException(status_code=400, detail="Roles can only be updated in private channels")
        
        # Get current user's role and validate permissions
        channel_info, roles = await role_service._get_channel_membership_info(
            db, channel_id, current_user["user_id"]
        )
        current_role = roles.get(current_user["user_id"])
        
        # Only owners can modify roles
        if current_role != ChannelRole.OWNER:
            raise HTTPException(status_code=400, detail="Only owners can modify roles")
        
        # Cannot modify own role
        if user_id == current_user["user_id"]:
            raise HTTPException(status_code=400, detail="Cannot modify your own role")
        
        # For owner role, verify there isn't already an owner
        if role_update.role == ChannelRole.OWNER:
            owner_count = await role_service._get_owner_count(db, channel_id)
            if owner_count > 0:
                raise HTTPException(status_code=400, detail="Private channels can only have one owner")
        
        # Update the role
        await role_service.update_member_role(
            db, channel_id, user_id, role_update.role, current_user["user_id"]
        )
        
        # Get updated member info
        member_info = await channel_service.get_member_info(db, channel_id, user_id)
        if not member_info:
            raise HTTPException(status_code=500, detail="Failed to retrieve updated member info")
            
        return member_info
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        debug_log("ERROR", f"Failed to update member role: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to update member role")

@router.post("/{channel_id}/transfer")
async def transfer_channel_ownership(
    channel_id: int,
    new_owner: ChannelMemberCreate,
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db)
):
    """Transfer channel ownership to another member.
    
    Only applicable to private channels:
    - Only the current owner can transfer ownership
    - The new owner must be a current member
    - The old owner becomes an admin
    """
    debug_log("TRANSFER", f"Starting ownership transfer for channel {channel_id}")
    debug_log("TRANSFER", f"├─ Current user: {current_user['user_id']}")
    debug_log("TRANSFER", f"├─ New owner: {new_owner.user_id}")
    
    try:
        await role_service.transfer_ownership(
            db, channel_id, current_user["user_id"], new_owner.user_id
        )
        debug_log("TRANSFER", "└─ Transfer completed successfully")
        return {"status": "success", "message": "Channel ownership transferred successfully"}
    except ValueError as e:
        debug_log("TRANSFER", f"└─ Transfer failed with ValueError: {str(e)}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        debug_log("TRANSFER", f"└─ Transfer failed with unexpected error: {str(e)}")
        debug_log("ERROR", f"Failed to transfer channel ownership: {str(e)}")
        raise HTTPException(status_code=500, detail="Failed to transfer channel ownership") 