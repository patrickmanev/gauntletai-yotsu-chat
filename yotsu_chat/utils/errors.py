from fastapi import HTTPException
from typing import Optional

class ErrorCode:
    # Auth errors (1000-1999)
    INVALID_CREDENTIALS = 1001
    TOKEN_EXPIRED = 1002
    INVALID_TOKEN = 1003
    INVALID_2FA = 1004
    UNAUTHORIZED = 1005
    FORBIDDEN = 1006
    
    # Message errors (2000-2999)
    MESSAGE_NOT_FOUND = 2001
    CHANNEL_NOT_FOUND = 2002
    INVALID_MESSAGE = 2003
    DUPLICATE_REACTION = 2004
    
    # Rate limiting (3000-3999)
    RATE_LIMIT_EXCEEDED = 3001
    
    # File errors (4000-4999)
    FILE_TOO_LARGE = 4001
    INVALID_FILE_TYPE = 4002
    FILE_NOT_FOUND = 4003
    
    # Presence errors (5000-5999)
    PRESENCE_UPDATE_FAILED = 5001

class YotsuError(HTTPException):
    def __init__(
        self,
        status_code: int,
        error_code: int,
        message: str,
        details: Optional[dict] = None
    ):
        self.error_code = error_code
        self.details = details
        super().__init__(
            status_code=status_code,
            detail={
                "error_code": error_code,
                "message": message,
                "details": details
            }
        )

def raise_unauthorized(message: str = "Not authorized", details: Optional[dict] = None):
    raise YotsuError(401, ErrorCode.UNAUTHORIZED, message, details)

def raise_forbidden(message: str = "Forbidden", details: Optional[dict] = None):
    raise YotsuError(403, ErrorCode.FORBIDDEN, message, details)

def raise_invalid_credentials(message: str = "Invalid credentials", details: Optional[dict] = None):
    raise YotsuError(401, ErrorCode.INVALID_CREDENTIALS, message, details)

def raise_invalid_2fa(message: str = "Invalid 2FA code", details: Optional[dict] = None):
    raise YotsuError(401, ErrorCode.INVALID_2FA, message, details)

def raise_rate_limit_exceeded(message: str = "Rate limit exceeded", details: Optional[dict] = None):
    raise YotsuError(429, ErrorCode.RATE_LIMIT_EXCEEDED, message, details)

def raise_invalid_file(message: str = "Invalid file", details: Optional[dict] = None):
    raise YotsuError(400, ErrorCode.INVALID_FILE_TYPE, message, details)

def raise_file_too_large(message: str = "File too large", details: Optional[dict] = None):
    raise YotsuError(400, ErrorCode.FILE_TOO_LARGE, message, details) 