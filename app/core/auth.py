from datetime import datetime, timedelta, UTC
from typing import Optional, Dict, Any
import bcrypt
from jose import jwt
import pyotp
from fastapi import HTTPException, Security, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import secrets
from fastapi import WebSocket
from fastapi import WebSocketDisconnect
import os

# Security configuration
SECRET_KEY = os.getenv("JWT_SECRET_KEY", secrets.token_urlsafe(32))
REFRESH_SECRET_KEY = os.getenv("JWT_REFRESH_SECRET_KEY", secrets.token_urlsafe(32))
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30
REFRESH_TOKEN_EXPIRE_MINUTES = 43200  # 30 days
TEMP_TOKEN_EXPIRE_MINUTES = 5

# Token tracking
used_refresh_tokens = set()  # Set of used refresh token JTIs

security = HTTPBearer()

def get_password_hash(password: str) -> str:
    """Hash a password with bcrypt"""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode(), salt).decode()

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash"""
    return bcrypt.checkpw(plain_password.encode(), hashed_password.encode())

def create_access_token(data: dict, expires_delta: timedelta = None):
    """Create a new JWT token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def create_refresh_token(data: dict) -> str:
    """Create a JWT refresh token with a unique JTI"""
    to_encode = data.copy()
    expire = datetime.now(UTC) + timedelta(minutes=REFRESH_TOKEN_EXPIRE_MINUTES)
    jti = secrets.token_urlsafe(16)  # Generate unique token ID
    to_encode.update({"exp": expire, "jti": jti})
    encoded_jwt = jwt.encode(to_encode, REFRESH_SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def verify_refresh_token(token: str) -> dict:
    """Verify a refresh token and check if it's been used"""
    try:
        payload = jwt.decode(token, REFRESH_SECRET_KEY, algorithms=[ALGORITHM])
        jti = payload.get("jti")
        if not jti:
            raise HTTPException(status_code=401, detail="Invalid refresh token")
        if jti in used_refresh_tokens:
            raise HTTPException(status_code=401, detail="Refresh token has been used")
        used_refresh_tokens.add(jti)  # Mark token as used
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Refresh token has expired")
    except jwt.JWTError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")

def decode_token(token: str) -> dict:
    """Decode and verify a JWT token"""
    try:
        decoded_token = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        return decoded_token
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token has expired")
    except jwt.JWTError:
        raise HTTPException(status_code=401, detail="Could not validate credentials")

def generate_totp_secret() -> str:
    """Generate a new TOTP secret"""
    return pyotp.random_base32()

def get_totp_uri(secret: str, email: str) -> str:
    """Get the TOTP URI for QR code generation"""
    totp = pyotp.TOTP(secret)
    return totp.provisioning_uri(email, issuer_name="Yotsu Chat")

def verify_totp(secret: str, token: str) -> bool:
    """Verify a TOTP token"""
    totp = pyotp.TOTP(secret)
    return totp.verify(token)

def create_temp_token(user_id: int):
    """Create a temporary token for 2FA verification."""
    to_encode = {
        "user_id": user_id,
        "temp": True,
        "exp": datetime.now(UTC) + timedelta(minutes=TEMP_TOKEN_EXPIRE_MINUTES)
    }
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get the current user from the JWT token."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        token = credentials.credentials
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("user_id")
        if user_id is None:
            raise credentials_exception
        # Check if this is a temporary token
        if payload.get("temp", False):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Temporary token not allowed for this operation"
            )
        return {"user_id": user_id}
    except jwt.JWTError:
        raise credentials_exception

async def get_current_temp_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get the current user from a temporary JWT token."""
    try:
        token = credentials.credentials
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("user_id")
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Could not validate credentials"
            )
        # Check if this is a temporary token
        if not payload.get("temp", False):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Only temporary tokens are allowed for this operation"
            )
        return {"user_id": user_id}
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired"
        )
    except jwt.JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials"
        )

async def get_current_user_ws(websocket: WebSocket) -> Dict[str, Any]:
    """Get current user from WebSocket connection token"""
    try:
        token = websocket.query_params.get("token")
        if not token:
            await websocket.close(code=1008)  # Policy violation
            raise WebSocketDisconnect(code=1008)
        
        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM]
        )
        
        user_id = payload.get("user_id")
        if not user_id:
            await websocket.close(code=1008)
            raise WebSocketDisconnect(code=1008)
        
        return {"user_id": int(user_id)}
        
    except jwt.JWTError:
        await websocket.close(code=1008)
        raise WebSocketDisconnect(code=1008) 