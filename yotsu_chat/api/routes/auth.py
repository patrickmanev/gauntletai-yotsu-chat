from fastapi import APIRouter, Depends, HTTPException
from ...core.auth import get_current_user, get_current_temp_user
from ...schemas.auth import (
    UserRegister, UserLogin, UserResponse,
    TokenResponse, TOTPVerify, RefreshRequest
)
from ...core.database import get_db
from ...core.config import get_settings
from ...services.auth_service import auth_service
from ...services.token_service import token_service
from ...utils import debug_log
from ...utils.validation import verify_users_exist
import aiosqlite
from jose import JWTError, ExpiredSignatureError
from datetime import datetime, UTC
from pydantic import BaseModel, EmailStr
from typing import Dict, Any, Optional
import logging
from ...services.channel_service import channel_service
from ...services.auth_service import auth_service

logger = logging.getLogger(__name__)
settings = get_settings()

# Temporary storage for users completing registration
temp_registrations: Dict[str, Dict[str, Any]] = {}

# Reduce temp token expiry to 5 minutes (300 seconds)
REGISTRATION_EXPIRY_SECONDS: int = 300

def cleanup_expired_registrations() -> None:
    """Remove expired registration attempts"""
    current_time = datetime.now(UTC).timestamp()
    expired_emails = [
        email for email, data in temp_registrations.items()
        if current_time - data["created_at"] > REGISTRATION_EXPIRY_SECONDS
    ]
    if expired_emails:
        debug_log("AUTH", f"Cleaning up {len(expired_emails)} expired registration attempts")
    for email in expired_emails:
        del temp_registrations[email]

class EmailCheck(BaseModel):
    email: EmailStr

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/check-email")
async def check_email(
    email_data: EmailCheck,
    db: aiosqlite.Connection = Depends(get_db)
) -> Dict[str, str]:
    """Check if an email is available for registration"""
    debug_log("AUTH", f"Checking email availability: {email_data.email}")
    async with db.execute(
        "SELECT 1 FROM users WHERE email = ?",
        (email_data.email,)
    ) as cursor:
        if await cursor.fetchone():
            debug_log("AUTH", f"Email already registered: {email_data.email}")
            raise HTTPException(
                status_code=409,
                detail="Email already registered"
            )
    debug_log("AUTH", f"Email available: {email_data.email}")
    return {"message": "Email is available"}

@router.post("/register", response_model=UserResponse, status_code=201)
async def register(
    user: UserRegister,
    db: aiosqlite.Connection = Depends(get_db)
) -> UserResponse:
    try:
        # Clean up any expired registration attempts first
        cleanup_expired_registrations()
        
        debug_log("AUTH", f"Registration attempt for: {user.email}")
        # Check if there's an existing registration attempt
        existing_attempt = temp_registrations.get(user.email)
        debug_log("AUTH", f"Found existing attempt: {bool(existing_attempt)}")
        
        if existing_attempt:
            debug_log("AUTH", "Comparing registration details")
            debug_log("AUTH", f"├─ Stored name: {existing_attempt['display_name']}")
            debug_log("AUTH", f"└─ New name: {user.display_name}")
            
            # If details match exactly, allow retry
            if (auth_service.verify_password(user.password, existing_attempt["password_hash"]) and
                existing_attempt["display_name"] == user.display_name):
                debug_log("AUTH", "Details match, allowing retry")
                # Return the same TOTP details for retry
                return UserResponse(
                    temp_token=token_service.create_temp_token(user.email),
                    totp_uri=auth_service.get_totp_uri(
                        existing_attempt["totp_secret"],
                        user.email
                    )
                )
            else:
                debug_log("AUTH", "Details do not match, blocking attempt")
                # If details don't match, block the attempt
                raise HTTPException(
                    status_code=429,
                    detail="Cannot register at the moment, please try again later."
                )
        
        # Check if email already exists in database
        async with db.execute(
            "SELECT 1 FROM users WHERE email = ?",
            (user.email,)
        ) as cursor:
            if await cursor.fetchone():
                debug_log("AUTH", f"Email already registered: {user.email}")
                raise HTTPException(status_code=400, detail="Email already registered")
        
        debug_log("AUTH", "Generating TOTP secret")
        # Generate TOTP secret
        totp_secret = auth_service.generate_totp_secret()
        totp_uri = auth_service.get_totp_uri(totp_secret, user.email)
        
        # Hash password
        password_hash = auth_service.get_password_hash(user.password)
        
        # Store registration data temporarily
        temp_token = token_service.create_temp_token(user.email)
        temp_registrations[user.email] = {
            "email": user.email,
            "password_hash": password_hash,
            "display_name": user.display_name,
            "totp_secret": totp_secret,
            "created_at": datetime.now(UTC).timestamp()
        }
        debug_log("AUTH", f"Stored temporary registration data for: {user.email}")
        
        return UserResponse(
            temp_token=temp_token,
            totp_uri=totp_uri
        )
    except HTTPException:
        raise
    except Exception as e:
        debug_log("ERROR", f"Registration failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/verify-2fa", response_model=TokenResponse)
async def verify_2fa(
    totp_data: TOTPVerify,
    current_user: Dict[str, Optional[Any]] = Depends(get_current_temp_user),
    db: aiosqlite.Connection = Depends(get_db)
) -> TokenResponse:
    try:
        debug_log("AUTH", f"2FA verification attempt: {current_user}")
        
        # Determine if this is a login or registration flow
        user_id = current_user.get("user_id")
        email = current_user.get("email")
        
        # Login flow - verify against database
        if user_id is not None:
            debug_log("AUTH", f"Login 2FA flow for user_id: {user_id}")
            
            # Get user's TOTP secret from database
            async with db.execute(
                "SELECT totp_secret FROM users WHERE user_id = ?",
                (user_id,)
            ) as cursor:
                user_data = await cursor.fetchone()
                if not user_data:
                    debug_log("AUTH", f"User not found for 2FA: {user_id}")
                    raise HTTPException(status_code=401, detail="Invalid TOTP code")
                
                debug_log("AUTH", "Verifying TOTP code against database secret")
                
                # In test mode, accept any code
                if settings.is_test_mode:
                    debug_log("AUTH", "Test mode, accepting any code")
                else:
                    # Verify TOTP code
                    if not auth_service.verify_totp(user_data["totp_secret"], totp_data.totp_code):
                        debug_log("AUTH", "TOTP verification failed")
                        raise HTTPException(status_code=401, detail="Invalid TOTP code")
                
                debug_log("AUTH", "TOTP verification successful")
                
                # Create tokens
                access_token = token_service.create_access_token({"user_id": user_id})
                refresh_token = token_service.create_refresh_token({"user_id": user_id})
                return TokenResponse(access_token=access_token, refresh_token=refresh_token)
        
        # Registration flow - verify against temp storage
        elif email is not None:
            debug_log("AUTH", f"Registration 2FA flow for email: {email}")
            
            # Clean up any expired registration attempts
            cleanup_expired_registrations()
            
            temp_data = temp_registrations.get(email)
            debug_log("AUTH", f"Found temp registration data: {bool(temp_data)}")
            
            if not temp_data:
                debug_log("AUTH", "Registration expired or invalid")
                raise HTTPException(status_code=401, detail="Invalid TOTP code")
            
            # Check if registration is expired (5 minutes)
            current_time = datetime.now(UTC).timestamp()
            if current_time - temp_data["created_at"] > REGISTRATION_EXPIRY_SECONDS:
                debug_log("AUTH", f"Registration expired. Created at: {temp_data['created_at']}")
                del temp_registrations[email]
                raise HTTPException(status_code=401, detail="Invalid TOTP code")
            
            debug_log("AUTH", "Verifying TOTP code")
            
            # In test mode, accept any code
            if settings.is_test_mode:
                debug_log("AUTH", "Test mode, accepting any code")
            else:
                # Verify TOTP code
                if not auth_service.verify_totp(temp_data["totp_secret"], totp_data.totp_code):
                    debug_log("AUTH", "TOTP verification failed")
                    raise HTTPException(status_code=401, detail="Invalid TOTP code")
            
            debug_log("AUTH", "TOTP verification successful")
            
            # Create user in database
            async with db.execute(
                """
                INSERT INTO users (email, password_hash, display_name, totp_secret)
                VALUES (?, ?, ?, ?)
                RETURNING user_id
                """,
                (temp_data["email"], temp_data["password_hash"], 
                 temp_data["display_name"], temp_data["totp_secret"])
            ) as cursor:
                user_data = await cursor.fetchone()
            
            # Create Notes channel for the user
            await channel_service.create_notes_channel(db, user_data["user_id"])
            
            await db.commit()
            
            debug_log("AUTH", f"Created user with ID: {user_data['user_id']}")
            debug_log("AUTH", f"├─ Email: {temp_data['email']}")
            debug_log("AUTH", f"└─ Display Name: {temp_data['display_name']}")
            
            # Clean up temp storage
            del temp_registrations[email]
            
            # Create tokens
            access_token = token_service.create_access_token({"user_id": user_data["user_id"]})
            refresh_token = token_service.create_refresh_token({"user_id": user_data["user_id"]})
            return TokenResponse(access_token=access_token, refresh_token=refresh_token)
        
        else:
            debug_log("AUTH", "Invalid token data for 2FA")
            raise HTTPException(status_code=401, detail="Invalid TOTP code")
            
    except HTTPException:
        raise
    except Exception as e:
        debug_log("ERROR", f"2FA verification failed: {str(e)}")
        raise HTTPException(status_code=401, detail="Invalid TOTP code")

@router.post("/login", response_model=TokenResponse)
async def login(
    user: UserLogin,
    db: aiosqlite.Connection = Depends(get_db)
) -> TokenResponse:
    debug_log("AUTH", f"Login attempt for: {user.email}")
    
    # Get user
    async with db.execute(
        """
        SELECT user_id, password_hash, totp_secret, email
        FROM users
        WHERE lower(email) = lower(?)
        """,
        (user.email,)
    ) as cursor:
        cursor.row_factory = aiosqlite.Row
        user_data = await cursor.fetchone()
        debug_log("AUTH", f"User lookup completed")
        debug_log("AUTH", f"User found: {bool(user_data)}")
        
        if not user_data:
            debug_log("AUTH", f"No user found for email: {user.email}")
            raise HTTPException(status_code=401, detail="Invalid email or password")
        
        debug_log("AUTH", "User details:")
        debug_log("AUTH", f"├─ Email: {user_data['email']}")
        debug_log("AUTH", f"├─ User ID: {user_data['user_id']}")
        debug_log("AUTH", f"└─ TOTP enabled: {bool(user_data['totp_secret'])}")
    
    # Verify password
    password_valid = auth_service.verify_password(user.password, user_data["password_hash"])
    
    if not password_valid:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    
    debug_log("AUTH", "Authentication successful")
    
    # In test mode, bypass 2FA and return access token directly
    if settings.is_test_mode:
        debug_log("AUTH", "Test mode, bypassing 2FA")
        access_token = token_service.create_access_token({"user_id": user_data["user_id"]})
        refresh_token = token_service.create_refresh_token({"user_id": user_data["user_id"]})
        return TokenResponse(access_token=access_token, refresh_token=refresh_token)
    
    # Create temporary token for 2FA
    debug_log("AUTH", "Creating temporary token for 2FA")
    temp_token = token_service.create_temp_token(user_data["user_id"])
    debug_log("AUTH", "Proceeding to 2FA verification")
    return TokenResponse(temp_token=temp_token)

@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(
    refresh_data: RefreshRequest,
    db: aiosqlite.Connection = Depends(get_db)
) -> TokenResponse:
    try:
        debug_log("AUTH", "Token refresh attempt")
        # Verify and invalidate refresh token
        payload = token_service.verify_refresh_token(refresh_data.refresh_token)
        user_id = payload.get("user_id")
        if not user_id:
            debug_log("AUTH", "Invalid refresh token: no user_id")
            raise HTTPException(status_code=401, detail="Invalid refresh token")
        
        # Check if user exists
        missing_users = await verify_users_exist(db, user_id)
        if missing_users:
            debug_log("AUTH", f"User {user_id} does not exist")
            raise HTTPException(status_code=401, detail="Invalid refresh token")
        
        # Get user info
        async with db.execute(
            """
            SELECT user_id, email, display_name, created_at
            FROM users
            WHERE user_id = ?
            """,
            (user_id,)
        ) as cursor:
            user_data = dict(await cursor.fetchone())
        
        debug_log("AUTH", f"Creating new tokens for user: {user_id}")
        # Create new tokens
        access_token = token_service.create_access_token({"user_id": user_id})
        refresh_token = token_service.create_refresh_token({"user_id": user_id})
        
        debug_log("AUTH", "Token refresh successful")
        return TokenResponse(access_token=access_token, refresh_token=refresh_token)
    except HTTPException:
        raise
    except ExpiredSignatureError:
        debug_log("AUTH", "Refresh token expired")
        raise HTTPException(status_code=401, detail="Refresh token has expired")
    except JWTError:
        debug_log("AUTH", "Invalid refresh token")
        raise HTTPException(status_code=401, detail="Invalid refresh token")
    except Exception as e:
        debug_log("ERROR", f"Token refresh failed: {str(e)}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.get("/verify")
async def verify_token(
    current_user: Dict[str, int] = Depends(get_current_user)
) -> Dict[str, Any]:
    """Verify if the current token is valid"""
    debug_log("AUTH", f"Token verification successful for user: {current_user['user_id']}")
    return {"valid": True, "user_id": current_user["user_id"]} 