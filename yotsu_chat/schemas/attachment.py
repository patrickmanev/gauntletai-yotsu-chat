from pydantic import BaseModel
from datetime import datetime

class AttachmentResponse(BaseModel):
    attachment_id: int
    message_id: int
    filename: str
    file_size: int
    content_type: str
    created_at: datetime 