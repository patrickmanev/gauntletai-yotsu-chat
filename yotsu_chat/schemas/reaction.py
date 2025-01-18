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

class MessageReactions(BaseModel):
    """Reactions for a single message, mapping emoji to list of user IDs."""
    reactions: Dict[str, List[int]] = Field(default_factory=dict)

class ReactionsList(BaseModel):
    """Response model for listing reactions across multiple messages."""
    reactions: Dict[int, MessageReactions] = Field(default_factory=dict) 