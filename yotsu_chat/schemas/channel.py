from enum import Enum
from pydantic import BaseModel, Field, model_validator
from typing import Optional, List, Union
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

    @model_validator(mode='after')
    def validate_update_fields(self) -> 'ChannelUpdate':
        """Validate channel name format."""
        validate_channel_name(self.name)
        return self

class ChannelMember(BaseModel):
    user_id: int
    display_name: str
    channel_id: int
    role: Optional[ChannelRole] = None
    joined_at: datetime

    @model_validator(mode='after')
    def validate_role_based_on_type(self) -> 'ChannelMember':
        """Roles are only used in private channels, will be None otherwise."""
        if self.role is not None and self.role not in [ChannelRole.OWNER, ChannelRole.ADMIN, ChannelRole.MEMBER]:
            raise ValueError("Invalid role for channel member")
        return self

class ChannelResponse(BaseModel):
    channel_id: int
    name: Optional[str] = None
    type: ChannelType
    created_at: Optional[datetime] = None
    created_by: Optional[int] = None

    @model_validator(mode='after')
    def validate_name_based_on_type(self) -> 'ChannelResponse':
        """Validate name field based on channel type."""
        if self.type in [ChannelType.DM, ChannelType.NOTES]:
            if self.name is not None:
                raise ValueError("DM and Notes channels must not have a name")
            # Ensure creation metadata is null for DM/Notes
            self.created_at = None
            self.created_by = None
        elif self.type in [ChannelType.PUBLIC, ChannelType.PRIVATE]:
            # Validate name format using validate_channel_name
            if self.name:
                self.name = validate_channel_name(self.name)
            else:
                raise ValueError("Public and Private channels must have a name")
            # Ensure creation metadata exists for Public/Private
            if not self.created_at or not self.created_by:
                raise ValueError("Public and Private channels must have creation metadata")
        return self

class ChannelMemberCreate(BaseModel):
    """Schema for adding a member to a channel."""
    user_id: int 

class AddMemberRequest(BaseModel):
    """Request model for adding one or more members to a channel."""
    user_ids: Union[int, List[int]]

class PublicChannelListResponse(BaseModel):
    """Minimal response model for listing public channels."""
    channel_id: int
    name: str