from typing import Dict, Optional, Tuple
import logging
import aiosqlite
from fastapi import HTTPException
import asyncio

from ..utils import debug_log
from ..utils.errors import YotsuError, raise_forbidden
from ..schemas.channel import ChannelRole, ChannelType
from ..core.ws_core import manager as ws_manager
from ..core.ws_events import create_event, RoleOwnershipTransferData, RoleUpdateData

logger = logging.getLogger(__name__)

class RoleService:
    def __init__(self):
        debug_log("ROLE", "Initializing role service")
        self._ownership_transfer_locks = {}  # Dict[int, asyncio.Lock] for channel-specific locks

    async def _get_transfer_lock(self, channel_id: int) -> asyncio.Lock:
        """Get or create a lock for channel ownership transfer."""
        if channel_id not in self._ownership_transfer_locks:
            self._ownership_transfer_locks[channel_id] = asyncio.Lock()
        return self._ownership_transfer_locks[channel_id]

    async def validate_member_addition(
        self,
        db: aiosqlite.Connection,
        channel_id: int,
        current_user_id: int,
        current_role: Optional[str] = None
    ) -> None:
        """Validate that a user has permission to add members to a private channel.
        
        Only owners and admins can add members to private channels.
        """
        debug_log("ROLE", f"Validating member addition for channel {channel_id}")
        debug_log("ROLE", f"├─ Current user: {current_user_id}")
        
        try:
            if not current_role:
                # Get current user's role
                async with db.execute(
                    "SELECT role FROM channels_members WHERE channel_id = ? AND user_id = ?",
                    [channel_id, current_user_id]
                ) as cursor:
                    result = await cursor.fetchone()
                    if not result:
                        debug_log("ROLE", "└─ User is not a member")
                        raise_forbidden("Not authorized to add members to this channel")
                    current_role = result[0]
            
            debug_log("ROLE", f"├─ User role: {current_role}")
            
            # Only owners and admins can add members
            if current_role not in [ChannelRole.OWNER, ChannelRole.ADMIN]:
                debug_log("ROLE", "└─ User lacks required role")
                raise_forbidden("Only owners and admins can add members to private channels")
            
            debug_log("ROLE", "└─ Validation successful")
            
        except YotsuError:
            raise
        except Exception as e:
            debug_log("ERROR", f"Failed to validate member addition: {str(e)}")
            raise HTTPException(status_code=500, detail="Failed to validate member addition")
    
    async def validate_member_removal(
        self,
        db: aiosqlite.Connection,
        channel_id: int,
        target_user_id: int,
        current_user_id: int
    ) -> None:
        """Validate that a user has permission to remove a member from a private channel.
        
        Rules:
        - Members can remove themselves (leave)
        - Owners can remove anyone except themselves
        - Admins can remove regular members
        """
        debug_log("ROLE", f"Validating member removal for channel {channel_id}")
        debug_log("ROLE", f"├─ Current user: {current_user_id}")
        debug_log("ROLE", f"├─ Target user: {target_user_id}")
        
        try:
            # Get current user's role
            async with db.execute(
                "SELECT role FROM channels_members WHERE channel_id = ? AND user_id = ?",
                [channel_id, current_user_id]
            ) as cursor:
                result = await cursor.fetchone()
                if not result:
                    debug_log("ROLE", "└─ Current user is not a member")
                    raise_forbidden("Not authorized to remove members from this channel")
                current_role = result[0]
            
            debug_log("ROLE", f"├─ Current user role: {current_role}")
            
            # Get target user's role
            async with db.execute(
                "SELECT role FROM channels_members WHERE channel_id = ? AND user_id = ?",
                [channel_id, target_user_id]
            ) as cursor:
                result = await cursor.fetchone()
                if not result:
                    debug_log("ROLE", "└─ Target user is not a member")
                    raise ValueError("Target user is not a member of the channel")
                target_role = result[0]
            
            debug_log("ROLE", f"├─ Target user role: {target_role}")
            
            # Self-removal is always allowed
            if current_user_id == target_user_id:
                debug_log("ROLE", "└─ Self-removal is allowed")
                return
            
            # Owners can remove anyone except themselves
            if current_role == ChannelRole.OWNER:
                debug_log("ROLE", "└─ Owner can remove anyone")
                return
            
            # Admins can only remove regular members
            if current_role == ChannelRole.ADMIN:
                if target_role not in [ChannelRole.MEMBER]:
                    debug_log("ROLE", "└─ Admin cannot remove owners/admins")
                    raise_forbidden("Admins can only remove regular members")
                debug_log("ROLE", "└─ Admin can remove regular members")
                return
            
            # Regular members cannot remove others
            debug_log("ROLE", "└─ Regular members cannot remove others")
            raise_forbidden("Regular members cannot remove other members")
            
        except YotsuError:
            raise
        except Exception as e:
            debug_log("ERROR", f"Failed to validate member removal: {str(e)}")
            raise HTTPException(status_code=500, detail="Failed to validate member removal")
    
    async def validate_role_update(
        self,
        db: aiosqlite.Connection,
        channel_id: int,
        target_user_id: int,
        current_user_id: int,
        new_role: str
    ) -> None:
        """Validate that a user has permission to update another member's role.
        
        Rules:
        - Only owners can modify roles
        - Cannot modify own role
        - Cannot have multiple owners
        """
        debug_log("ROLE", f"Validating role update for channel {channel_id}")
        debug_log("ROLE", f"├─ Current user: {current_user_id}")
        debug_log("ROLE", f"├─ Target user: {target_user_id}")
        debug_log("ROLE", f"├─ New role: {new_role}")
        
        try:
            # Get current user's role
            async with db.execute(
                "SELECT role FROM channels_members WHERE channel_id = ? AND user_id = ?",
                [channel_id, current_user_id]
            ) as cursor:
                result = await cursor.fetchone()
                if not result:
                    debug_log("ROLE", "└─ Current user is not a member")
                    raise_forbidden("Not authorized to update roles in this channel")
                current_role = result[0]
            
            debug_log("ROLE", f"├─ Current user role: {current_role}")
            
            # Only owners can modify roles
            if current_role != ChannelRole.OWNER:
                debug_log("ROLE", "└─ Only owners can modify roles")
                raise_forbidden("Only owners can modify roles")
            
            # Cannot modify own role
            if current_user_id == target_user_id:
                debug_log("ROLE", "└─ Cannot modify own role")
                raise_forbidden("Cannot modify your own role")
            
            # For owner role, verify there isn't already an owner
            if new_role == ChannelRole.OWNER:
                owner_count = await self._get_owner_count(db, channel_id)
                if owner_count > 0:
                    debug_log("ROLE", "└─ Cannot have multiple owners")
                    raise_forbidden("Private channels can only have one owner")
            
            debug_log("ROLE", "└─ Validation successful")
            
        except YotsuError:
            raise
        except Exception as e:
            debug_log("ERROR", f"Failed to validate role update: {str(e)}")
            raise HTTPException(status_code=500, detail="Failed to validate role update")
    
    async def validate_channel_update(
        self,
        db: aiosqlite.Connection,
        channel_id: int,
        current_user_id: int
    ) -> None:
        """Validate that a user has permission to update a private channel.
        
        Only owners can update private channels.
        """
        debug_log("ROLE", f"Validating channel update for channel {channel_id}")
        debug_log("ROLE", f"├─ Current user: {current_user_id}")
        
        try:
            # Get current user's role
            async with db.execute(
                "SELECT role FROM channels_members WHERE channel_id = ? AND user_id = ?",
                [channel_id, current_user_id]
            ) as cursor:
                result = await cursor.fetchone()
                if not result:
                    debug_log("ROLE", "└─ User is not a member")
                    raise_forbidden("Not authorized to update this channel")
                role = result[0]
            
            debug_log("ROLE", f"├─ User role: {role}")
            
            # Only owners can update private channels
            if role != ChannelRole.OWNER:
                debug_log("ROLE", "└─ Only owners can update private channels")
                raise_forbidden("Only owners can update private channels")
            
            debug_log("ROLE", "└─ Validation successful")
            
        except YotsuError:
            raise
        except Exception as e:
            debug_log("ERROR", f"Failed to validate channel update: {str(e)}")
            raise HTTPException(status_code=500, detail="Failed to validate channel update")
    
    async def validate_ownership_transfer(
        self,
        db: aiosqlite.Connection,
        channel_id: int,
        target_user_id: int,
        current_user_id: int
    ) -> None:
        """Validate that a user has permission to transfer channel ownership.
        
        Rules:
        - Only the current owner can transfer ownership
        - The new owner must be a current member
        """
        debug_log("ROLE", f"Validating ownership transfer for channel {channel_id}")
        debug_log("ROLE", f"├─ Current user: {current_user_id}")
        debug_log("ROLE", f"├─ Target user: {target_user_id}")
        
        try:
            # Get current user's role
            async with db.execute(
                "SELECT role FROM channels_members WHERE channel_id = ? AND user_id = ?",
                [channel_id, current_user_id]
            ) as cursor:
                result = await cursor.fetchone()
                if not result:
                    debug_log("ROLE", "└─ Current user is not a member")
                    raise_forbidden("Not authorized to transfer ownership of this channel")
                current_role = result[0]
            
            debug_log("ROLE", f"├─ Current user role: {current_role}")
            
            # Only the current owner can transfer ownership
            if current_role != ChannelRole.OWNER:
                debug_log("ROLE", "└─ Only owners can transfer ownership")
                raise_forbidden("Only the current owner can transfer ownership")
            
            # Verify target user is a member
            async with db.execute(
                "SELECT 1 FROM channels_members WHERE channel_id = ? AND user_id = ?",
                [channel_id, target_user_id]
            ) as cursor:
                if not await cursor.fetchone():
                    debug_log("ROLE", "└─ Target user is not a member")
                    raise ValueError("Target user must be a member of the channel")
            
            debug_log("ROLE", "└─ Validation successful")
            
        except YotsuError:
            raise
        except Exception as e:
            debug_log("ERROR", f"Failed to validate ownership transfer: {str(e)}")
            raise HTTPException(status_code=500, detail="Failed to validate ownership transfer")
    
    async def update_member_role(
        self,
        db: aiosqlite.Connection,
        channel_id: int,
        user_id: int,
        new_role: str,
        current_user_id: int
    ) -> None:
        """Update a member's role in a private channel.
        
        Rules:
        - Only owners can modify roles
        - Cannot modify own role
        - Cannot have multiple owners
        """
        debug_log("ROLE", f"Updating role for user {user_id} in channel {channel_id}")
        debug_log("ROLE", f"├─ New role: {new_role}")
        
        try:
            # Get current user's role
            async with db.execute(
                "SELECT role FROM channels_members WHERE channel_id = ? AND user_id = ?",
                [channel_id, current_user_id]
            ) as cursor:
                result = await cursor.fetchone()
                if not result:
                    debug_log("ROLE", "└─ Current user is not a member")
                    raise HTTPException(
                        status_code=422,
                        detail=[{"msg": "Not authorized to update roles in this channel"}]
                    )
                current_role = result[0]
            
            debug_log("ROLE", f"├─ Current user role: {current_role}")
            
            # Only owners can modify roles
            if current_role != ChannelRole.OWNER:
                debug_log("ROLE", "└─ Only owners can modify roles")
                raise HTTPException(
                    status_code=422,
                    detail=[{"msg": "Only the owner can modify roles"}]
                )
            
            # Cannot modify own role
            if current_user_id == user_id:
                debug_log("ROLE", "└─ Cannot modify own role")
                raise HTTPException(
                    status_code=422,
                    detail=[{"msg": "Cannot modify your own role"}]
                )
            
            # For owner role, verify there isn't already an owner
            if new_role == ChannelRole.OWNER:
                owner_count = await self._get_owner_count(db, channel_id)
                if owner_count > 0:
                    debug_log("ROLE", "└─ Cannot have multiple owners")
                    raise HTTPException(
                        status_code=422,
                        detail=[{"msg": "Private channels can only have one owner"}]
                    )
            
            # Update role
            await db.execute(
                """
                UPDATE channels_members
                SET role = ?
                WHERE channel_id = ? AND user_id = ?
                """,
                (new_role, channel_id, user_id)
            )
            await db.commit()
            
            # Broadcast role update event
            event = create_event(
                "role.update",
                RoleUpdateData(
                    channel_id=channel_id,
                    user_id=user_id,
                    role=new_role
                )
            )
            await ws_manager.broadcast_to_subscribers(channel_id, event)
            debug_log("ROLE", "├─ Broadcasted role update event")
            
            debug_log("ROLE", "└─ Role updated successfully")
            
        except HTTPException:
            await db.rollback()
            raise
        except Exception as e:
            debug_log("ERROR", f"Failed to update member role: {str(e)}")
            await db.rollback()
            raise HTTPException(
                status_code=500,
                detail="Failed to update member role"
            )
    
    async def transfer_ownership(
        self,
        db: aiosqlite.Connection,
        channel_id: int,
        new_owner_id: int,
        current_owner_id: int
    ) -> None:
        """Transfer channel ownership to another member.
        
        Rules:
        1. Can only be called for a private channel
        2. Can only be called by the channel owner
        3. Can only be called once at a time by a given owner user
        4. Target user is promoted to owner, regardless if they were admin or member
        5. Previous owner becomes an admin
        """
        debug_log("ROLE", f"Transferring ownership of channel {channel_id}")
        debug_log("ROLE", f"├─ Current owner: {current_owner_id}")
        debug_log("ROLE", f"├─ New owner: {new_owner_id}")
        
        try:
            # Get channel type and verify it's private
            async with db.execute(
                "SELECT type FROM channels WHERE channel_id = ?",
                [channel_id]
            ) as cursor:
                result = await cursor.fetchone()
                if not result:
                    raise ValueError("Channel not found")
                if result[0] != ChannelType.PRIVATE:
                    raise ValueError("Ownership can only be transferred in private channels")
            
            # Get current user's role
            async with db.execute(
                "SELECT role FROM channels_members WHERE channel_id = ? AND user_id = ?",
                [channel_id, current_owner_id]
            ) as cursor:
                result = await cursor.fetchone()
                if not result or result[0] != ChannelRole.OWNER:
                    raise_forbidden("Only the current owner can transfer ownership")
            
            # Verify target user is a member
            async with db.execute(
                "SELECT 1 FROM channels_members WHERE channel_id = ? AND user_id = ?",
                [channel_id, new_owner_id]
            ) as cursor:
                if not await cursor.fetchone():
                    raise ValueError("Target user must be a member of the channel")
            
            # Acquire lock for this channel's ownership transfer
            lock = await self._get_transfer_lock(channel_id)
            async with lock:
                # Update roles in a transaction
                await db.execute(
                    """
                    UPDATE channels_members
                    SET role = ?
                    WHERE channel_id = ? AND user_id = ?
                    """,
                    (ChannelRole.OWNER, channel_id, new_owner_id)
                )
                
                await db.execute(
                    """
                    UPDATE channels_members
                    SET role = ?
                    WHERE channel_id = ? AND user_id = ?
                    """,
                    (ChannelRole.ADMIN, channel_id, current_owner_id)
                )
                
                await db.commit()
                
                # Validate the transfer was successful
                async with db.execute(
                    """
                    SELECT user_id, role 
                    FROM channels_members 
                    WHERE channel_id = ? AND user_id IN (?, ?)
                    """,
                    [channel_id, new_owner_id, current_owner_id]
                ) as cursor:
                    roles = {row[0]: row[1] async for row in cursor}
                    
                    if roles.get(new_owner_id) != ChannelRole.OWNER:
                        raise ValueError("Failed to transfer ownership: new owner role not set")
                    if roles.get(current_owner_id) != ChannelRole.ADMIN:
                        raise ValueError("Failed to transfer ownership: previous owner role not updated")
                
                # Broadcast ownership transfer event
                event = create_event(
                    "role.ownership_transferred",
                    RoleOwnershipTransferData(
                        channel_id=channel_id,
                        new_owner_id=new_owner_id,
                        previous_owner_id=current_owner_id
                    )
                )
                await ws_manager.broadcast_to_subscribers(channel_id, event)
                debug_log("ROLE", "├─ Broadcasted ownership transfer event")
                
                debug_log("ROLE", "└─ Ownership transferred successfully")
            
        except Exception as e:
            debug_log("ERROR", f"Failed to transfer ownership: {str(e)}")
            await db.rollback()
            raise HTTPException(
                status_code=500 if not isinstance(e, (ValueError, YotsuError)) else 400,
                detail=str(e)
            )
    
    async def _get_owner_count(self, db: aiosqlite.Connection, channel_id: int) -> int:
        """Get the number of owners for a channel."""
        async with db.execute(
            """
            SELECT COUNT(*) 
            FROM channels_members 
            WHERE channel_id = ? AND role = ?
            """,
            (channel_id, ChannelRole.OWNER)
        ) as cursor:
            return (await cursor.fetchone())[0]

# Global instance
role_service = RoleService() 