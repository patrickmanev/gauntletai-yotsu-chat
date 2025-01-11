from typing import Optional, Dict, Tuple
import logging
import aiosqlite
from ..utils import debug_log
from ..schemas.channel import ChannelRole, ChannelType
from ..utils.errors import YotsuError, ErrorCode

logger = logging.getLogger(__name__)

class RoleService:
    def __init__(self):
        debug_log("ROLE", "Initializing role service")
    
    async def _get_channel_membership_info(
        self,
        db: aiosqlite.Connection,
        channel_id: int,
        *user_ids: int
    ) -> Tuple[Dict, Dict[int, Optional[str]]]:
        """Get channel type and member roles in a single query.
        Returns: (channel_info, {user_id: role})
        
        This optimized helper:
        1. Gets channel type and info
        2. Gets roles for all requested users
        3. Validates channel type
        4. All in a single database query
        """
        debug_log("ROLE", f"Getting membership info for channel {channel_id}, users {user_ids}")
        
        try:
            # Build the role subqueries for each user
            role_selects = []
            params = []
            
            for i, user_id in enumerate(user_ids):
                role_selects.append(f"""
                    (SELECT role 
                     FROM channels_members 
                     WHERE channel_id = c.channel_id 
                     AND user_id = ?) as role_{i}
                """)
                params.append(user_id)
            
            # Add channel_id last to match WHERE clause
            params.append(channel_id)
            
            # Construct and execute query
            query = f"""
                SELECT 
                    c.channel_id,
                    c.type
                    {', ' + ', '.join(role_selects) if role_selects else ''}
                FROM channels c
                WHERE c.channel_id = ?
            """
            
            async with db.execute(query, params) as cursor:
                row = await cursor.fetchone()
                if not row:
                    return None, {}
                
                # Extract channel info
                channel_info = {
                    'channel_id': row[0],
                    'type': row[1]
                }
                
                # Extract roles for each user
                roles = {}
                for i, user_id in enumerate(user_ids):
                    roles[user_id] = row[i + 2] if len(row) > i + 2 else None
                
                debug_log("ROLE", f"Channel info: {channel_info}, Roles: {roles}")
                return channel_info, roles
                
        except Exception as e:
            debug_log("ERROR", f"Failed to get channel membership info: {str(e)}", exc_info=True)
            raise
    
    async def validate_member_addition(
        self,
        db: aiosqlite.Connection,
        channel_id: int,
        current_user_id: int
    ) -> None:
        """Validate if the current user can add members to a private channel."""
        debug_log("ROLE", f"Validating member addition for channel {channel_id}")
        debug_log("ROLE", f"├─ Current user: {current_user_id}")
        
        # Get channel info and current user's role
        channel_info, roles = await self._get_channel_membership_info(
            db, channel_id, current_user_id
        )
        
        debug_log("ROLE", f"├─ Channel info: {channel_info}")
        debug_log("ROLE", f"├─ User roles: {roles}")
        
        if not channel_info:
            debug_log("ROLE", "└─ Channel not found")
            raise ValueError("Channel not found")
            
        if current_user_id not in roles:
            debug_log("ROLE", "└─ User is not a member")
            raise YotsuError(403, ErrorCode.UNAUTHORIZED, "You must be a member to add others")
        
        current_role = roles[current_user_id]
        debug_log("ROLE", f"├─ Current user role: {current_role}")
        
        # Only owners and admins can add members
        if current_role not in [ChannelRole.OWNER, ChannelRole.ADMIN]:
            debug_log("ROLE", "└─ User lacks required role (owner/admin)")
            raise YotsuError(403, ErrorCode.UNAUTHORIZED, "Only owners and admins can add members")
        
        debug_log("ROLE", "└─ Validation successful")

    async def validate_member_removal(
        self,
        db: aiosqlite.Connection,
        channel_id: int,
        target_user_id: int,
        current_user_id: int
    ) -> None:
        """Validate if user can remove another user from a private channel.
        
        Rules:
        - Owners can remove anyone except themselves (must transfer ownership first)
        - Admins can remove only non-roled members
        - Members cannot remove anyone
        - Anyone can remove themselves (except owners)
        """
        channel_info, roles = await self._get_channel_membership_info(
            db, channel_id, current_user_id, target_user_id
        )
        
        if channel_info["type"] != ChannelType.PRIVATE:
            return  # Only validate private channels
            
        current_role = roles.get(current_user_id)
        target_role = roles.get(target_user_id)
        
        if not current_role:
            raise ValueError("You must be a member of the channel")
            
        # Self-removal case
        if current_user_id == target_user_id:
            if current_role == ChannelRole.OWNER:
                raise ValueError("Channel owner must transfer ownership before leaving")
            return
            
        # Removing others case
        if current_role == ChannelRole.OWNER:
            return  # Owners can remove anyone else
            
        if current_role == ChannelRole.ADMIN:
            if target_role and target_role != ChannelRole.MEMBER:  # Only block if target has a privileged role
                raise ValueError("Admins can only remove regular members")
            return
            
        raise ValueError("Only owners and admins can remove members")

    async def _get_owner_count(
        self,
        db: aiosqlite.Connection,
        channel_id: int
    ) -> int:
        """Get the number of owners in a channel."""
        async with db.execute(
            """
            SELECT COUNT(*) 
            FROM channels_members 
            WHERE channel_id = ? AND role = ?
            """,
            (channel_id, ChannelRole.OWNER.value)
        ) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else 0

    async def update_member_role(
        self,
        db: aiosqlite.Connection,
        channel_id: int,
        target_user_id: int,
        new_role: str,
        current_user_id: int
    ) -> None:
        """Update a member's role in a private channel.
        
        Rules:
        - Only applicable to private channels
        - Only owners can promote/demote members to/from admin
        - Owners cannot modify their own role
        - Admins cannot modify roles
        - Cannot promote to owner (use transfer_ownership instead)
        - Only one owner per private channel
        
        Args:
            db: Database connection
            channel_id: Channel ID
            target_user_id: User ID to update role for
            new_role: New role to assign
            current_user_id: User ID performing the update
            
        Raises:
            ValueError: If validation fails or operation is not permitted
        """
        channel_info, roles = await self._get_channel_membership_info(
            db, channel_id, current_user_id, target_user_id
        )
        
        if channel_info["type"] != ChannelType.PRIVATE:
            raise ValueError("Roles can only be updated in private channels")
            
        current_role = roles.get(current_user_id)
        target_role = roles.get(target_user_id)
        
        if not current_role:
            raise ValueError("You must be a member of the channel")
            
        # Convert string role to enum for proper comparison
        try:
            current_role_enum = ChannelRole(current_role)
            new_role_enum = ChannelRole(new_role)
        except ValueError:
            raise ValueError("Invalid role value")
            
        if current_role_enum != ChannelRole.OWNER:
            raise ValueError("Only owners can modify roles")
            
        if current_user_id == target_user_id:
            raise ValueError("Cannot modify your own role")
            
        if new_role_enum == ChannelRole.OWNER:
            # Check if there's already an owner
            owner_count = await self._get_owner_count(db, channel_id)
            if owner_count > 0:
                raise ValueError("Private channels can only have one owner")
            
        if not target_role:
            raise ValueError("Target user must be a member of the channel")
            
        # Execute update directly without nested transaction
        await db.execute(
            """
            UPDATE channels_members
            SET role = ?
            WHERE channel_id = ? AND user_id = ?
            """,
            (new_role_enum.value, channel_id, target_user_id)
        )
        await db.commit()
        debug_log("ROLE", f"Updated role for user {target_user_id} to {new_role}")

    async def transfer_ownership(
        self,
        db: aiosqlite.Connection,
        channel_id: int,
        current_owner_id: int,
        new_owner_id: int
    ) -> None:
        """Transfer channel ownership to another member.
        
        Only applicable to private channels:
        - Only the current owner can transfer ownership
        - The new owner must be a current member
        - The old owner becomes an admin
        - There can only be one owner at a time
        
        Raises:
            ValueError: If validation fails or operation is not permitted
        """
        debug_log("TRANSFER", f"Validating transfer request for channel {channel_id}")
        debug_log("TRANSFER", f"├─ Current owner: {current_owner_id}")
        debug_log("TRANSFER", f"├─ New owner: {new_owner_id}")
        
        # First validate channel type and roles
        channel_info, roles = await self._get_channel_membership_info(
            db, channel_id, current_owner_id, new_owner_id
        )
        debug_log("TRANSFER", f"├─ Channel info: {channel_info}")
        debug_log("TRANSFER", f"├─ Roles: {roles}")
        
        if channel_info["type"] != ChannelType.PRIVATE:
            debug_log("TRANSFER", "└─ Failed: Not a private channel")
            raise ValueError("Ownership transfer is only available for private channels")
        
        current_role = roles.get(current_owner_id)
        if current_role != ChannelRole.OWNER:
            debug_log("TRANSFER", "└─ Failed: Current user not owner")
            raise ValueError("Only the current owner can transfer ownership")

        # Check if there are any other members first
        async with db.execute(
            """
            SELECT COUNT(*) 
            FROM channels_members 
            WHERE channel_id = ? AND user_id != ?
            """,
            (channel_id, current_owner_id)
        ) as cursor:
            row = await cursor.fetchone()
            if row[0] == 0:
                debug_log("TRANSFER", "└─ Failed: No other members")
                raise ValueError("Cannot transfer ownership: channel has no other members")
        
        # Then check if new owner is a member
        new_owner_role = roles.get(new_owner_id)
        if not new_owner_role:
            debug_log("TRANSFER", "└─ Failed: New owner not a member")
            raise ValueError("New owner must be a current member of the channel")

        try:
            debug_log("TRANSFER", "├─ Starting transaction")
            # Start immediate transaction after all validations pass
            try:
                await db.execute("BEGIN IMMEDIATE TRANSACTION")
                debug_log("TRANSFER", "├─ Transaction started successfully")
                
                # Check again for other owners now that we have the lock
                async with db.execute(
                    """
                    SELECT COUNT(*) 
                    FROM channels_members 
                    WHERE channel_id = ? AND role = ? AND user_id != ?
                    """,
                    (channel_id, ChannelRole.OWNER.value, current_owner_id)
                ) as cursor:
                    row = await cursor.fetchone()
                    if row[0] > 0:
                        debug_log("TRANSFER", "└─ Failed: Another owner exists")
                        await db.execute("ROLLBACK")
                        debug_log("TRANSFER", "└─ Rolled back transaction")
                        raise ValueError("Transfer in progress, please try again later")
                
                # Update new owner first
                debug_log("TRANSFER", "├─ Updating new owner role")
                await db.execute(
                    """
                    UPDATE channels_members
                    SET role = ?
                    WHERE channel_id = ? AND user_id = ?
                    """,
                    (ChannelRole.OWNER.value, channel_id, new_owner_id)
                )
                
                # Update old owner to admin
                debug_log("TRANSFER", "├─ Updating old owner role")
                await db.execute(
                    """
                    UPDATE channels_members
                    SET role = ?
                    WHERE channel_id = ? AND user_id = ?
                    """,
                    (ChannelRole.ADMIN.value, channel_id, current_owner_id)
                )
                
                debug_log("TRANSFER", "├─ Committing transaction")
                await db.execute("COMMIT")
                debug_log("TRANSFER", "└─ Transfer completed successfully")
            except aiosqlite.OperationalError as e:
                if "database is locked" in str(e):
                    debug_log("TRANSFER", "└─ Failed: Database locked (transfer in progress)")
                    raise ValueError("Transfer in progress, please try again later")
                debug_log("TRANSFER", f"└─ Failed: Database error: {str(e)}")
                raise ValueError("Failed to start transfer - database error")
        except Exception as e:
            debug_log("TRANSFER", f"├─ Rolling back due to error: {str(e)}")
            if not str(e).startswith("Transfer in progress"):  # Only rollback if we haven't already
                await db.execute("ROLLBACK")
            if isinstance(e, ValueError):
                raise
            debug_log("ERROR", f"Failed to transfer channel ownership: {str(e)}")
            raise

# Global instance
role_service = RoleService() 