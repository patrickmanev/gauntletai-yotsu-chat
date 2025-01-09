from pydantic import BaseModel, Field
import emoji
from typing import List, Dict

class ReactionCreate(BaseModel):
    emoji: str = Field(..., description="The emoji to react with")
    
    def validate_emoji(self):
        if not emoji.is_emoji(self.emoji):
            raise ValueError("Invalid emoji provided")
        return self.emoji

class ReactionResponse(BaseModel):
    message_id: int
    emoji: str
    user_id: int
    created_at: str

class ReactionCount(BaseModel):
    emoji: str
    count: int
    users: List[int] 