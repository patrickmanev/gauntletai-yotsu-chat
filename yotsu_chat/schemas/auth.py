from pydantic import BaseModel, EmailStr, validator
import re

class UserRegister(BaseModel):
    email: EmailStr
    password: str
    display_name: str

    @validator('display_name')
    def validate_display_name(cls, v):
        if len(v) > 25:
            raise ValueError("Display name must not exceed 25 characters")
        if not re.match(r"^[a-zA-Z']+(?:\s[a-zA-Z']+)*$", v):
            raise ValueError("Display name must contain only English letters, apostrophes, and single spaces between names")
        return v

    @validator('password')
    def validate_password(cls, v):
        requirements = [
            (len(v) >= 8, "be at least 8 characters long"),
            (bool(re.search(r'[A-Z]', v)), "contain at least one uppercase letter"),
            (bool(re.search(r'[a-z]', v)), "contain at least one lowercase letter"),
            (bool(re.search(r'\d', v)), "contain at least one number"),
            (bool(re.search(r'[!@#$%^&*(),.?":{}|<>]', v)), "contain at least one special character.")
        ]
        
        failed = [req for (check, req) in requirements if not check]
        if failed:
            criteria = ", ".join(failed)
            raise ValueError(f"Password does not meet security criteria. Password must: {criteria}")
        return v

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    user_id: int
    totp_secret: str
    totp_uri: str

class TokenResponse(BaseModel):
    access_token: str | None = None
    temp_token: str | None = None
    refresh_token: str | None = None

class TOTPVerify(BaseModel):
    totp_code: str

class RefreshRequest(BaseModel):
    refresh_token: str 