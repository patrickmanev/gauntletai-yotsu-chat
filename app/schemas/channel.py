from enum import Enum
from pydantic import BaseModel, Field, validator
from typing import Optional, List
from datetime import datetime
import re

def validate_channel_name(name: str) -> str:
    if not re.match(r'^[a-zA-Z0-9]+(?:-[a-zA-Z0-9]+)*$', name):
        raise ValueError("Channel name must be alphanumeric and can only contain hyphens between characters")
    return name

class ChannelType(str, Enum):
    PUBLIC = "public"
    PRIVATE = "private"

class ChannelRole(str, Enum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"

class ChannelCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=50)
    type: ChannelType = Field(default=ChannelType.PUBLIC)
    initial_members: Optional[List[int]] = Field(default=None, description="List of user IDs to add to the channel")

    _validate_name = validator('name', allow_reuse=True)(validate_channel_name)

class ChannelUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=50)
    type: Optional[ChannelType] = None

    _validate_name = validator('name', allow_reuse=True)(validate_channel_name)

class ChannelMember(BaseModel):
    user_id: int
    display_name: str
    role: ChannelRole
    joined_at: datetime

class ChannelResponse(BaseModel):
    channel_id: int
    name: str
    type: ChannelType
    created_at: datetime
    is_member: bool
    role: Optional[ChannelRole] = None

class ChannelMemberUpdate(BaseModel):
    role: ChannelRole 

class ChannelMemberCreate(BaseModel):
    user_id: int
    role: str = "member"  # Default to member role 