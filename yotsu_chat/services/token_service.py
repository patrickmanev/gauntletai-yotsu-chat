from datetime import datetime, timedelta, UTC
from typing import Dict, Any, Optional
import secrets
from jose import jwt
from fastapi import HTTPException, status, WebSocket
from fastapi.security import HTTPBearer
from fastapi import WebSocketDisconnect
import logging

from ..utils import debug_log
from ..core.config import get_settings
from .auth_service import auth_service

logger = logging.getLogger(__name__)
settings = get_settings()

security = HTTPBearer()

class TokenService:
    def create_access_token(self, data: dict, expires_delta: Optional[timedelta] = None) -> str:
        """Create a new JWT access token."""
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.now(UTC) + expires_delta
        else:
            expire = datetime.now(UTC) + timedelta(minutes=settings.jwt.access_token_expire_minutes)
        to_encode.update({"exp": expire})
        return jwt.encode(
            to_encode,
            settings.jwt.access_token_secret_key,
            algorithm=settings.jwt.token_algorithm
        )

    def create_refresh_token(self, data: dict) -> str:
        """Create a JWT refresh token with a unique JTI."""
        to_encode = data.copy()
        expire = datetime.now(UTC) + timedelta(days=settings.jwt.refresh_token_expire_days)
        jti = secrets.token_urlsafe(16)  # Generate unique token ID
        to_encode.update({"exp": expire, "jti": jti})
        return jwt.encode(
            to_encode,
            settings.jwt.refresh_token_secret_key,
            algorithm=settings.jwt.token_algorithm
        )

    def verify_refresh_token(self, token: str) -> dict:
        """Verify a refresh token and check if it's been used."""
        try:
            payload = jwt.decode(
                token,
                settings.jwt.refresh_token_secret_key,
                algorithms=[settings.jwt.token_algorithm]
            )
            jti = payload.get("jti")
            if not jti:
                raise HTTPException(status_code=401, detail="Invalid refresh token")
            if auth_service.is_refresh_token_used(jti):
                raise HTTPException(status_code=401, detail="Refresh token has been used")
            auth_service.mark_refresh_token_as_used(jti)
            return payload
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Refresh token has expired")
        except jwt.JWTError:
            raise HTTPException(status_code=401, detail="Invalid refresh token")

    def decode_token(self, token: str) -> dict:
        """Decode and verify a JWT access token."""
        try:
            decoded_token = jwt.decode(
                token,
                settings.jwt.access_token_secret_key,
                algorithms=[settings.jwt.token_algorithm]
            )
            return decoded_token
        except jwt.ExpiredSignatureError:
            raise HTTPException(status_code=401, detail="Token has expired")
        except jwt.JWTError:
            raise HTTPException(status_code=401, detail="Could not validate credentials")

    def create_temp_token(self, data: str | int) -> str:
        """Create a temporary token for 2FA verification."""
        to_encode = {
            "temp": True,
            "exp": datetime.now(UTC) + timedelta(minutes=settings.jwt.temp_token_expire_minutes)
        }
        
        # Add either user_id or email based on the type of data
        if isinstance(data, int):
            to_encode["user_id"] = data
        else:
            to_encode["email"] = data
            
        return jwt.encode(
            to_encode,
            settings.jwt.temp_token_secret_key,
            algorithm=settings.jwt.token_algorithm
        )

    async def get_current_user(self, token: str) -> Dict[str, Any]:
        """Get the current user from the JWT token."""
        try:
            payload = jwt.decode(
                token,
                settings.jwt.access_token_secret_key,
                algorithms=[settings.jwt.token_algorithm]
            )
            user_id = payload.get("user_id")
            if user_id is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Could not validate credentials"
                )
            # Check if this is a temporary token
            if payload.get("temp", False):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Temporary token not allowed for this operation"
                )
            return {"user_id": user_id}
        except jwt.JWTError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials"
            )

    async def get_current_temp_user(self, token: str) -> Dict[str, Any]:
        """Get the current user from a temporary JWT token."""
        try:
            payload = jwt.decode(
                token,
                settings.jwt.temp_token_secret_key,
                algorithms=[settings.jwt.token_algorithm]
            )
            
            # Check if this is a temporary token
            if not payload.get("temp", False):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid TOTP code"
                )
            
            # Handle both user_id and email in payload
            user_id = payload.get("user_id")
            email = payload.get("email")
            
            if not (user_id or email):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid TOTP code"
                )
            
            return {"user_id": user_id, "email": email}
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid TOTP code"
            )
        except jwt.JWTError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid TOTP code"
            )

    async def get_current_user_ws(self, websocket: WebSocket) -> Dict[str, Any]:
        """Get current user from WebSocket connection token."""
        try:
            token = websocket.query_params.get("token")
            if not token:
                await websocket.close(code=1008)  # Policy violation
                raise WebSocketDisconnect(code=1008)
            
            payload = jwt.decode(
                token,
                settings.jwt.access_token_secret_key,
                algorithms=[settings.jwt.token_algorithm]
            )
            
            user_id = payload.get("user_id")
            if not user_id:
                await websocket.close(code=1008)
                raise WebSocketDisconnect(code=1008)
            
            return {"user_id": int(user_id)}
            
        except jwt.JWTError:
            await websocket.close(code=1008)
            raise WebSocketDisconnect(code=1008)

token_service = TokenService() 