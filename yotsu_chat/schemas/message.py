from pydantic import BaseModel, Field, validator, model_validator
from datetime import datetime
from typing import Optional, List

class MessageCreate(BaseModel):
    content: str
    parent_id: Optional[int] = None
    channel_id: Optional[int] = Field(None, description="Channel to send message to")
    recipient_id: Optional[int] = Field(None, description="User to send DM to")

    @validator('content')
    def validate_content(cls, v):
        if not v or not v.strip():
            raise ValueError("Message content cannot be empty")
        return v.strip()

class MessageUpdate(BaseModel):
    content: str

class MessageResponse(BaseModel):
    message_id: int
    channel_id: int
    user_id: int
    content: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    display_name: str
    parent_id: Optional[int] = None
    has_reactions: bool = False
    is_deleted: bool = False  # For soft-deleted messages

class MessageWithAttachments(MessageResponse):
    attachments: List[dict] = [] 