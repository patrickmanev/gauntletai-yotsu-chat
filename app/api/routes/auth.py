from fastapi import APIRouter, Depends, HTTPException
from app.core.auth import (
    get_current_user, get_current_temp_user,
    create_access_token, create_temp_token, create_refresh_token,
    get_password_hash, verify_password, verify_totp, verify_refresh_token,
    REFRESH_SECRET_KEY, ALGORITHM
)
from app.schemas.auth import (
    UserRegister, UserLogin, UserResponse,
    TokenResponse, TOTPVerify, RefreshRequest
)
from app.core.database import get_db
import pyotp
import aiosqlite
from jose import jwt, JWTError, ExpiredSignatureError
from app.core.config import get_settings
import os
from datetime import datetime, UTC

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/register", response_model=UserResponse, status_code=201)
async def register(user: UserRegister, db: aiosqlite.Connection = Depends(get_db)):
    try:
        # Check if email already exists
        async with db.execute(
            "SELECT 1 FROM users WHERE email = ?",
            (user.email,)
        ) as cursor:
            if await cursor.fetchone():
                raise HTTPException(status_code=400, detail="Email already registered")
        
        # Generate TOTP secret
        totp_secret = pyotp.random_base32()
        totp = pyotp.TOTP(totp_secret)
        totp_uri = totp.provisioning_uri(
            name=user.email,
            issuer_name="Yotsu Chat"
        )
        
        # Hash password
        password_hash = get_password_hash(user.password)
        
        # Create user
        async with db.execute(
            """
            INSERT INTO users (email, password_hash, display_name, totp_secret)
            VALUES (?, ?, ?, ?)
            RETURNING user_id
            """,
            (user.email, password_hash, user.display_name, totp_secret)
        ) as cursor:
            user_data = await cursor.fetchone()
        
        await db.commit()
        
        return UserResponse(
            user_id=user_data["user_id"],
            totp_secret=totp_secret,
            totp_uri=totp_uri
        )
    except aiosqlite.IntegrityError:
        raise HTTPException(status_code=400, detail="Email already registered")
    except HTTPException:
        raise  # Re-raise HTTP exceptions
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/login", response_model=TokenResponse)
async def login(user: UserLogin, db: aiosqlite.Connection = Depends(get_db)):
    # Get user
    async with db.execute(
        """
        SELECT user_id, password_hash
        FROM users
        WHERE email = ?
        """,
        (user.email,)
    ) as cursor:
        user_data = await cursor.fetchone()
        if not user_data:
            raise HTTPException(status_code=401, detail="Invalid email or password")
    
    # Verify password
    if not verify_password(user.password, user_data["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    # In test mode, bypass 2FA and return access token directly
    if os.getenv("TEST_MODE") == "true":
        access_token = create_access_token({"user_id": user_data["user_id"]})
        refresh_token = create_refresh_token({"user_id": user_data["user_id"]})
        return TokenResponse(access_token=access_token, refresh_token=refresh_token)
    
    # Create temporary token for 2FA
    temp_token = create_temp_token(user_data["user_id"])
    return TokenResponse(temp_token=temp_token)

@router.post("/verify-2fa", response_model=TokenResponse)
async def verify_2fa(
    totp_data: TOTPVerify,
    current_user: dict = Depends(get_current_temp_user),
    db: aiosqlite.Connection = Depends(get_db)
):
    try:
        user_id = current_user["user_id"]
        
        # Get user's TOTP secret
        async with db.execute(
            "SELECT totp_secret FROM users WHERE user_id = ?",
            (user_id,)
        ) as cursor:
            user_data = await cursor.fetchone()
            if not user_data:
                raise HTTPException(status_code=401, detail="User not found")
        
        # In test mode, accept any code
        if os.getenv("TEST_MODE") == "true":
            access_token = create_access_token({"user_id": user_id})
            refresh_token = create_refresh_token({"user_id": user_id})
            return TokenResponse(access_token=access_token, refresh_token=refresh_token)
        
        # Verify TOTP code
        if not verify_totp(user_data["totp_secret"], totp_data.totp_code):
            raise HTTPException(status_code=401, detail="Invalid TOTP code")
        
        # Create tokens
        access_token = create_access_token({"user_id": user_id})
        refresh_token = create_refresh_token({"user_id": user_id})
        
        return TokenResponse(access_token=access_token, refresh_token=refresh_token)
    except HTTPException:
        raise  # Re-raise HTTP exceptions
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    refresh_data: RefreshRequest,
    db: aiosqlite.Connection = Depends(get_db)
):
    try:
        # Verify and invalidate refresh token
        payload = verify_refresh_token(refresh_data.refresh_token)
        user_id = payload.get("user_id")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid refresh token")
        
        # Check if user exists
        async with db.execute(
            "SELECT 1 FROM users WHERE user_id = ?",
            (user_id,)
        ) as cursor:
            if not await cursor.fetchone():
                raise HTTPException(status_code=401, detail="User not found")
        
        # Create new tokens
        access_token = create_access_token({"user_id": user_id})
        refresh_token = create_refresh_token({"user_id": user_id})
        
        return TokenResponse(access_token=access_token, refresh_token=refresh_token)
    except HTTPException:
        raise  # Re-raise HTTP exceptions
    except ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Refresh token has expired")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    except Exception as e:
        raise HTTPException(status_code=500, detail="Internal server error") 