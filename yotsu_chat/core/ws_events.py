from typing import TypeVar, Generic, Optional, Dict, Any, Literal, List
from pydantic import BaseModel, Field, model_validator
from datetime import datetime, UTC
from ..schemas.channel import ChannelType

# Generic type for event data
T = TypeVar('T')

class EventSource(BaseModel):
    """Source information for an event."""
    connection_id: Optional[str] = None
    user_id: Optional[int] = None

class EventMetadata(BaseModel):
    """Metadata for all events."""
    source: EventSource
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    version: Literal[1] = 1

class WSEvent(BaseModel, Generic[T]):
    """Base WebSocket event structure."""
    type: str
    data: T
    metadata: EventMetadata

# Common event data types
class MessageData(BaseModel):
    """Data for message.created events."""
    message_id: int
    channel_id: int
    user_id: int
    content: str
    parent_id: Optional[int] = None
    created_at: datetime

class MessageUpdateData(BaseModel):
    """Data for message.updated events."""
    message_id: int
    content: str
    updated_at: datetime

class MessageDeleteData(BaseModel):
    """Data for message.deleted events."""
    message_id: int
    channel_id: int

class MemberEventData(BaseModel):
    """Data for member.joined and member.left events."""
    channel_id: int
    user_id: int
    display_name: str
    role: Optional[str] = None

class ChannelUpdateData(BaseModel):
    """Data for channel.update events."""
    channel_id: int
    name: Optional[str] = None
    type: ChannelType

class ReactionData(BaseModel):
    """Data for reaction.added and reaction.removed events."""
    message_id: int
    emoji: str
    user_id: int

class RoleUpdateData(BaseModel):
    """Data for role.update events."""
    channel_id: int
    user_id: int
    role: str

class RoleOwnershipTransferData(BaseModel):
    """Data for role.ownership_transferred events."""
    channel_id: int
    new_owner_id: int
    previous_owner_id: int

class SystemErrorData(BaseModel):
    """Data for system.error events."""
    code: int
    message: str

class PresenceData(BaseModel):
    """Data for presence events.
    
    Can be used for both individual updates and bulk presence information:
    - For individual updates: provide user_id and status
    - For initial/bulk presence: provide online_users list
    """
    user_id: Optional[int] = None
    status: Optional[Literal["online", "offline"]] = None
    online_users: Optional[List[int]] = None
    
    @model_validator(mode='after')
    def validate_presence_data(self) -> 'PresenceData':
        """Validate that either individual update or bulk presence data is provided."""
        if (self.user_id is not None and self.status is not None) == (self.online_users is not None):
            raise ValueError("Must provide either (user_id and status) OR online_users list, but not both")
        return self

class ChannelInitData(BaseModel):
    """Data for channel.init event, sent when a channel is created with initial members.
    
    Members list contains:
    - user_id: int
    - display_name: str
    - role: Optional[str] (only present for private channels)
    """
    channel_id: int
    name: str
    type: ChannelType
    members: List[Dict[str, Any]]  # List of member info including user_id, display_name, and optional role

# Event type literals for better type checking
EventType = Literal[
    "message.created",
    "message.updated",
    "message.deleted",
    "message.soft_deleted",
    "member.joined",
    "member.left",
    "channel.update",
    "reaction.added",
    "reaction.removed",
    "role.update",
    "role.ownership_transferred",
    "system.error",
    "presence",
    "ping",
    "pong",
    "connection_id"
]

def create_event(type: EventType, data: T, source: Optional[EventSource] = None) -> WSEvent[T]:
    """Create a new WebSocket event with the standard structure."""
    if source is None:
        source = EventSource()
    
    return WSEvent(
        type=type,
        data=data,
        metadata=EventMetadata(source=source)
    ) 