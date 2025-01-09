from pydantic import BaseModel
from datetime import datetime
from typing import Optional, List

class MessageCreate(BaseModel):
    content: str
    parent_id: Optional[int] = None

class MessageUpdate(BaseModel):
    content: str

class MessageResponse(BaseModel):
    message_id: int
    channel_id: int
    user_id: int
    content: str
    created_at: datetime
    edited_at: Optional[datetime] = None
    display_name: str
    parent_id: Optional[int] = None

class MessageWithAttachments(MessageResponse):
    attachments: List[dict] = [] 