from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    # JWT Settings
    access_token_secret_key: str = "your-access-token-secret-key"  # Change in production
    refresh_token_secret_key: str = "your-refresh-token-secret-key"  # Change in production
    temp_token_secret_key: str = "your-temp-token-secret-key"  # Change in production
    token_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 30
    temp_token_expire_minutes: int = 5

    # File Upload Settings
    max_file_size: int = 20 * 1024 * 1024  # 20MB
    upload_directory: str = "uploads"

    # Rate Limiting
    rate_limit_window_seconds: int = 60
    rate_limit_max_requests: int = 100

    class Config:
        env_file = ".env"

@lru_cache()
def get_settings() -> Settings:
    return Settings() 