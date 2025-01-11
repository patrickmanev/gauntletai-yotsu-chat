from enum import Enum
from pydantic import BaseModel, Field, validator, model_validator
from typing import Optional, List
from datetime import datetime
import re
from yotsu_chat.core.config import get_settings

class ChannelType(str, Enum):
    PUBLIC = "public"
    PRIVATE = "private"
    DM = "dm"
    NOTES = "notes"

class ChannelRole(str, Enum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"

def validate_channel_name(name: str) -> str:
    """Validate channel name format:
    - Lowercase alphanumeric words separated by single dashes
    - Must start and end with a word
    - No consecutive dashes
    - Max length defined in settings
    """
    if not name:
        raise ValueError("Channel name is required for public and private channels")
    
    settings = get_settings()
    if len(name) > settings.channel.max_name_length:
        raise ValueError(f"Channel name cannot exceed {settings.channel.max_name_length} characters")
    
    if name != name.lower():
        raise ValueError("Channel name must be lowercase")
    
    if not re.match(r'^[a-z0-9]+(-[a-z0-9]+)*$', name):
        raise ValueError("Channel name must be lowercase alphanumeric words separated by single dashes")
    
    return name

class ChannelCreate(BaseModel):
    name: Optional[str] = Field(None)
    type: ChannelType = Field(default=ChannelType.PUBLIC)
    initial_members: Optional[List[int]] = Field(default=None, description="List of user IDs to add to the channel")

    @model_validator(mode='after')
    def validate_channel_fields(self) -> 'ChannelCreate':
        """Validate channel fields based on type."""
        if self.type in [ChannelType.NOTES, ChannelType.DM]:
            raise ValueError(f"Cannot create {self.type.value} channels directly")
        
        # Public and Private channels must have a valid name
        if self.type in [ChannelType.PUBLIC, ChannelType.PRIVATE]:
            if not self.name:
                raise ValueError(f"{self.type.value} channels must have a name")
            settings = get_settings()
            if len(self.name) > settings.channel.max_name_length:
                raise ValueError(f"Channel name cannot exceed {settings.channel.max_name_length} characters")
            if self.name != self.name.lower():
                raise ValueError("Channel name must be lowercase")
            if not re.match(r'^[a-z0-9]+(-[a-z0-9]+)*$', self.name):
                raise ValueError("Channel name must be lowercase alphanumeric words separated by single dashes")
        elif self.name is not None:
            raise ValueError(f"{self.type.value} channels cannot have a name")
        
        return self

class ChannelUpdate(BaseModel):
    name: str
    channel_type: ChannelType  # Used for validation only, not for updates

    @model_validator(mode='after')
    def validate_update_fields(self) -> 'ChannelUpdate':
        """Validate channel name format."""
        # Validate name format
        validate_channel_name(self.name)
        return self

class ChannelMember(BaseModel):
    user_id: int
    display_name: str
    role: Optional[ChannelRole] = None
    joined_at: datetime
    channel_type: ChannelType

    @model_validator(mode='after')
    def validate_role_based_on_type(self) -> 'ChannelMember':
        """Validate roles only for private channels."""
        if self.channel_type == ChannelType.PRIVATE:
            if not self.role:
                raise ValueError("Private channel members must have a role")
            if self.role not in [ChannelRole.OWNER, ChannelRole.ADMIN, ChannelRole.MEMBER]:
                raise ValueError("Invalid role for private channel member")
        elif self.channel_type != ChannelType.PRIVATE:
            self.role = None
        return self

class ChannelResponse(BaseModel):
    channel_id: int
    name: Optional[str] = None
    type: ChannelType
    role: Optional[ChannelRole] = None
    created_at: datetime
    created_by: int
    is_member: bool = True

    @model_validator(mode='after')
    def validate_role_based_on_type(self) -> 'ChannelResponse':
        """Validate roles only for private channels."""
        if self.type == ChannelType.PRIVATE and self.is_member:
            if not self.role:
                raise ValueError("Private channel members must have a role")
            if self.role not in [ChannelRole.OWNER, ChannelRole.ADMIN, ChannelRole.MEMBER]:
                raise ValueError("Invalid role for private channel member")
        elif self.type != ChannelType.PRIVATE:
            self.role = None
        return self

class ChannelMemberUpdate(BaseModel):
    """Schema for updating a member's role in a channel."""
    role: ChannelRole = Field(..., description="The new role to assign to the member")

    @model_validator(mode='after')
    def validate_role(self) -> 'ChannelMemberUpdate':
        """Validate that the role is a valid enum value."""
        if not isinstance(self.role, ChannelRole):
            raise ValueError("Invalid role value")
        return self

class ChannelMemberCreate(BaseModel):
    """Schema for adding a member to a channel."""
    user_id: int 