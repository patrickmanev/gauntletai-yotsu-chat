from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer
import logging

from ..services.token_service import token_service, security

logger = logging.getLogger(__name__)

def decode_token(token: str):
    """Decode and validate a JWT token."""
    return token_service.decode_token(token)

async def get_current_user(credentials = Depends(security)):
    """FastAPI dependency for getting the current user from JWT token."""
    return await token_service.get_current_user(credentials.credentials)

async def get_current_temp_user(credentials = Depends(security)):
    """FastAPI dependency for getting the current user from a temporary JWT token."""
    return await token_service.get_current_temp_user(credentials.credentials)

async def get_current_user_ws(websocket):
    """FastAPI dependency for getting the current user from WebSocket connection."""
    return await token_service.get_current_user_ws(websocket) 