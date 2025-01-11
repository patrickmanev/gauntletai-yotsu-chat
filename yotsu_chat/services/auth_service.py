from datetime import datetime, timedelta, UTC
import bcrypt
import pyotp
import logging
from typing import Dict, Any, Optional
from fastapi import HTTPException, status

from ..utils import debug_log
from ..core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

class AuthService:
    def __init__(self):
        """Initialize the auth service."""
        self._used_refresh_tokens = set()  # Set of used refresh token JTIs
    
    def get_password_hash(self, password: str) -> str:
        """Hash a password with bcrypt."""
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode(), salt).decode()
    
    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a password against its hash."""
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
    
    def generate_totp_secret(self) -> str:
        """Generate a new TOTP secret."""
        return pyotp.random_base32()
    
    def get_totp_uri(self, secret: str, email: str) -> str:
        """Get the TOTP URI for QR code generation."""
        totp = pyotp.TOTP(secret)
        return totp.provisioning_uri(email, issuer_name="Yotsu Chat")
    
    def verify_totp(self, secret: str, token: str) -> bool:
        """Verify a TOTP token."""
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
    
    def mark_refresh_token_as_used(self, jti: str) -> None:
        """Mark a refresh token as used."""
        self._used_refresh_tokens.add(jti)
    
    def is_refresh_token_used(self, jti: str) -> bool:
        """Check if a refresh token has been used."""
        return jti in self._used_refresh_tokens
    
    def cleanup_used_tokens(self, max_size: int = 10000) -> None:
        """Cleanup used tokens if the set gets too large.
        This is a simple implementation - in production, you'd want a proper cleanup strategy.
        """
        if len(self._used_refresh_tokens) > max_size:
            self._used_refresh_tokens.clear()

auth_service = AuthService() 