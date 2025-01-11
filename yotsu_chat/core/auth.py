from datetime import datetime, timedelta, UTC
from typing import Dict, Any
import bcrypt
from jose import jwt
import pyotp
from fastapi import HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
import secrets
from fastapi import WebSocket
from fastapi import WebSocketDisconnect

from .config import get_settings
from .database import debug_log

# Get settings instance
settings = get_settings()

# Token tracking
used_refresh_tokens = set()  # Set of used refresh token JTIs

security = HTTPBearer()

def get_password_hash(password: str) -> str:
    """Hash a password with bcrypt"""
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode(), salt).decode()

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against its hash"""
    try:
        debug_log("AUTH", "Starting password verification")
        
        # Check for valid UTF-8 encoding
        try:
            plain_password.encode()
            hashed_password.encode()
        except UnicodeEncodeError as e:
            debug_log("AUTH", f"Password encoding error: {str(e)}")
            return False
            
        # Verify password
        result = bcrypt.checkpw(plain_password.encode(), hashed_password.encode())
        debug_log("AUTH", f"Password verification {'succeeded' if result else 'failed'}")
        return result
        
    except Exception as e:
        debug_log("ERROR", f"Password verification error: {str(e)}")
        return False

def create_access_token(data: dict, expires_delta: timedelta = None):
    """Create a new JWT token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(minutes=settings.jwt.access_token_expire_minutes)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.jwt.access_token_secret_key, algorithm=settings.jwt.token_algorithm)
    return encoded_jwt

def create_refresh_token(data: dict) -> str:
    """Create a JWT refresh token with a unique JTI"""
    to_encode = data.copy()
    expire = datetime.now(UTC) + timedelta(days=settings.jwt.refresh_token_expire_days)
    jti = secrets.token_urlsafe(16)  # Generate unique token ID
    to_encode.update({"exp": expire, "jti": jti})
    encoded_jwt = jwt.encode(to_encode, settings.jwt.refresh_token_secret_key, algorithm=settings.jwt.token_algorithm)
    return encoded_jwt

def verify_refresh_token(token: str) -> dict:
    """Verify a refresh token and check if it's been used"""
    try:
        payload = jwt.decode(token, settings.jwt.refresh_token_secret_key, algorithms=[settings.jwt.token_algorithm])
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
        decoded_token = jwt.decode(token, settings.jwt.access_token_secret_key, algorithms=[settings.jwt.token_algorithm])
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
    current_time = datetime.now()
    debug_log("AUTH", "TOTP Verification:")
    debug_log("AUTH", f"├─ Secret: {secret}")
    debug_log("AUTH", f"├─ Received token: {token}")
    debug_log("AUTH", f"├─ Current time: {current_time}")
    debug_log("AUTH", f"├─ Expected token: {totp.now()}")
    debug_log("AUTH", f"├─ Previous token: {totp.at(current_time - timedelta(seconds=30))}")
    debug_log("AUTH", f"└─ Next token: {totp.at(current_time + timedelta(seconds=30))}")
    result = totp.verify(token)
    debug_log("AUTH", f"Verification result: {'success' if result else 'failed'}")
    return result

def create_temp_token(data: str | int):
    """Create a temporary token for 2FA verification.
    Args:
        data: Either a user_id (int) or email (str)
    """
    to_encode = {
        "temp": True,
        "exp": datetime.now(UTC) + timedelta(minutes=settings.jwt.temp_token_expire_minutes)
    }
    
    # Add either user_id or email based on the type of data
    if isinstance(data, int):
        to_encode["user_id"] = data
    else:
        to_encode["email"] = data
        
    return jwt.encode(to_encode, settings.jwt.temp_token_secret_key, algorithm=settings.jwt.token_algorithm)

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    """Get the current user from the JWT token."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        token = credentials.credentials
        payload = jwt.decode(token, settings.jwt.access_token_secret_key, algorithms=[settings.jwt.token_algorithm])
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
        payload = jwt.decode(token, settings.jwt.temp_token_secret_key, algorithms=[settings.jwt.token_algorithm])
        
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

async def get_current_user_ws(websocket: WebSocket) -> Dict[str, Any]:
    """Get current user from WebSocket connection token"""
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