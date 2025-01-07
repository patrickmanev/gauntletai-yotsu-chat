from pydantic import BaseModel, EmailStr

class UserRegister(BaseModel):
    email: EmailStr
    password: str
    display_name: str

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