from fastapi import APIRouter, Depends, HTTPException
from yotsu_chat.core.auth import get_current_user
from yotsu_chat.schemas.channel import ChannelCreate, ChannelResponse, ChannelMember, ChannelMemberCreate, ChannelRole
from yotsu_chat.core.database import get_db
from typing import List
import aiosqlite
from datetime import datetime

router = APIRouter(prefix="/channels", tags=["channels"])

@router.post("", response_model=ChannelResponse, status_code=201)
async def create_channel(
    channel: ChannelCreate,
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db)
):
    try:
        # Check for duplicate channel name
        async with db.execute(
            "SELECT 1 FROM channels WHERE name = ?",
            (channel.name,)
        ) as cursor:
            if await cursor.fetchone():
                raise HTTPException(status_code=400, detail="Channel name already exists")
        
        # Create channel
        async with db.execute(
            """
            INSERT INTO channels (name, type)
            VALUES (?, ?)
            RETURNING channel_id, name, type, created_at
            """,
            (channel.name, channel.type)
        ) as cursor:
            channel_data = await cursor.fetchone()
        
        # Add creator as owner
        await db.execute(
            """
            INSERT INTO channels_members (channel_id, user_id, role)
            VALUES (?, ?, ?)
            """,
            (channel_data["channel_id"], current_user["user_id"], ChannelRole.OWNER)
        )
        
        # Add initial members if provided
        if hasattr(channel, 'initial_members') and channel.initial_members:
            for member_id in channel.initial_members:
                # Skip if member is the creator
                if member_id == current_user["user_id"]:
                    continue
                
                # Verify member exists
                async with db.execute(
                    "SELECT 1 FROM users WHERE user_id = ?",
                    (member_id,)
                ) as cursor:
                    if not await cursor.fetchone():
                        continue  # Skip non-existent users
                
                # Add member with default role
                await db.execute(
                    """
                    INSERT INTO channels_members (channel_id, user_id, role)
                    VALUES (?, ?, ?)
                    """,
                    (channel_data["channel_id"], member_id, ChannelRole.MEMBER)
                )
        
        await db.commit()
        
        return ChannelResponse(
            channel_id=channel_data["channel_id"],
            name=channel_data["name"],
            type=channel_data["type"],
            created_at=channel_data["created_at"],
            is_member=True,  # Creator is always a member
            role=ChannelRole.OWNER  # Creator is always the owner
        )
    except aiosqlite.IntegrityError as e:
        await db.rollback()
        raise HTTPException(status_code=400, detail="Channel creation failed due to constraint violation")
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/{channel_id}/members", response_model=ChannelMember)
async def add_channel_member(
    channel_id: int,
    member: ChannelMemberCreate,
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db)
):
    # Check if channel exists
    async with db.execute(
        "SELECT 1 FROM channels WHERE channel_id = ?",
        (channel_id,)
    ) as cursor:
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Channel not found")
    
    # Check if current user is owner or admin
    async with db.execute(
        """
        SELECT role FROM channels_members
        WHERE channel_id = ? AND user_id = ? AND role IN ('owner', 'admin')
        """,
        (channel_id, current_user["user_id"])
    ) as cursor:
        if not await cursor.fetchone():
            raise HTTPException(
                status_code=403,
                detail="Only channel owners and admins can add members"
            )
    
    # Check if user exists and get display name
    async with db.execute(
        "SELECT display_name FROM users WHERE user_id = ?",
        (member.user_id,)
    ) as cursor:
        user_data = await cursor.fetchone()
        if not user_data:
            raise HTTPException(status_code=404, detail="User not found")
    
    # Check if user is already a member
    async with db.execute(
        "SELECT 1 FROM channels_members WHERE channel_id = ? AND user_id = ?",
        (channel_id, member.user_id)
    ) as cursor:
        if await cursor.fetchone():
            raise HTTPException(
                status_code=400,
                detail="User is already a member of this channel"
            )
    
    # Get current timestamp
    now = datetime.utcnow()
    
    # Add member
    await db.execute(
        """
        INSERT INTO channels_members (channel_id, user_id, role, joined_at)
        VALUES (?, ?, ?, ?)
        """,
        (channel_id, member.user_id, member.role, now)
    )
    await db.commit()
    
    return ChannelMember(
        user_id=member.user_id,
        display_name=user_data["display_name"],
        role=member.role,
        joined_at=now
    )

@router.get("", response_model=List[ChannelResponse])
async def list_channels(
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db)
):
    async with db.execute(
        """
        SELECT c.channel_id, c.name, c.type, c.created_at, cm.role
        FROM channels c
        JOIN channels_members cm ON c.channel_id = cm.channel_id
        WHERE cm.user_id = ?
        """,
        (current_user["user_id"],)
    ) as cursor:
        channels = await cursor.fetchall()
    
    return [
        ChannelResponse(
            channel_id=channel["channel_id"],
            name=channel["name"],
            type=channel["type"],
            created_at=str(channel["created_at"]),
            is_member=True,  # We're only listing channels the user is a member of
            role=channel["role"]
        )
        for channel in channels
    ]

@router.get("/{channel_id}", response_model=ChannelResponse)
async def get_channel(
    channel_id: int,
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db)
):
    # Get channel details with member info
    async with db.execute(
        """
        SELECT c.channel_id, c.name, c.type, c.created_at, cm.role
        FROM channels c
        JOIN channels_members cm ON c.channel_id = cm.channel_id
        WHERE c.channel_id = ? AND cm.user_id = ?
        """,
        (channel_id, current_user["user_id"])
    ) as cursor:
        channel = await cursor.fetchone()
        if not channel:
            raise HTTPException(
                status_code=403,
                detail="You are not a member of this channel"
            )
    
    return ChannelResponse(
        channel_id=channel["channel_id"],
        name=channel["name"],
        type=channel["type"],
        created_at=str(channel["created_at"]),
        is_member=True,  # We're only showing channels the user is a member of
        role=channel["role"]
    )

@router.get("/{channel_id}/members", response_model=List[ChannelMember])
async def list_channel_members(
    channel_id: int,
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db)
):
    # Check if user is a member
    async with db.execute(
        "SELECT 1 FROM channels_members WHERE channel_id = ? AND user_id = ?",
        (channel_id, current_user["user_id"])
    ) as cursor:
        if not await cursor.fetchone():
            raise HTTPException(
                status_code=403,
                detail="You are not a member of this channel"
            )
    
    # Get members with display names
    async with db.execute(
        """
        SELECT cm.user_id, cm.role, cm.joined_at, u.display_name
        FROM channels_members cm
        JOIN users u ON cm.user_id = u.user_id
        WHERE cm.channel_id = ?
        """,
        (channel_id,)
    ) as cursor:
        members = await cursor.fetchall()
    
    return [
        ChannelMember(
            user_id=member["user_id"],
            display_name=member["display_name"],
            role=member["role"],
            joined_at=member["joined_at"]
        )
        for member in members
    ]

@router.put("/{channel_id}", response_model=ChannelResponse)
async def update_channel(
    channel_id: int,
    channel: ChannelCreate,
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db)
):
    # Check if user is owner or admin
    async with db.execute(
        """
        SELECT role FROM channels_members
        WHERE channel_id = ? AND user_id = ? AND role IN ('owner', 'admin')
        """,
        (channel_id, current_user["user_id"])
    ) as cursor:
        member = await cursor.fetchone()
        if not member:
            raise HTTPException(
                status_code=403,
                detail="Only channel owners and admins can update channel details"
            )
    
    # Update channel
    await db.execute(
        """
        UPDATE channels
        SET name = ?, type = ?
        WHERE channel_id = ?
        """,
        (channel.name, channel.type, channel_id)
    )
    await db.commit()
    
    # Get updated channel details
    async with db.execute(
        """
        SELECT c.channel_id, c.name, c.type, c.created_at, cm.role
        FROM channels c
        JOIN channels_members cm ON c.channel_id = cm.channel_id
        WHERE c.channel_id = ? AND cm.user_id = ?
        """,
        (channel_id, current_user["user_id"])
    ) as cursor:
        channel_data = await cursor.fetchone()
        if not channel_data:
            raise HTTPException(status_code=404, detail="Channel not found")
    
    return ChannelResponse(
        channel_id=channel_data["channel_id"],
        name=channel_data["name"],
        type=channel_data["type"],
        created_at=str(channel_data["created_at"]),
        is_member=True,  # We're only showing channels the user is a member of
        role=channel_data["role"]
    )

@router.delete("/{channel_id}/members/{user_id}")
async def remove_channel_member(
    channel_id: int,
    user_id: int,
    current_user: dict = Depends(get_current_user),
    db: aiosqlite.Connection = Depends(get_db)
):
    # Check if channel exists and user has permission
    async with db.execute(
        """
        SELECT role FROM channels_members
        WHERE channel_id = ? AND user_id = ? AND role IN ('owner', 'admin')
        """,
        (channel_id, current_user["user_id"])
    ) as cursor:
        if not await cursor.fetchone():
            raise HTTPException(
                status_code=403,
                detail="Only channel owners and admins can remove members"
            )
    
    # Check if target user is a member
    async with db.execute(
        "SELECT 1 FROM channels_members WHERE channel_id = ? AND user_id = ?",
        (channel_id, user_id)
    ) as cursor:
        if not await cursor.fetchone():
            raise HTTPException(status_code=404, detail="Member not found")
    
    # Remove member
    await db.execute(
        "DELETE FROM channels_members WHERE channel_id = ? AND user_id = ?",
        (channel_id, user_id)
    )
    await db.commit()
    
    return {"status": "success"} 