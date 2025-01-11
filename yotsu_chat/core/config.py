from enum import Enum
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings
from functools import lru_cache
from pydantic import Extra

class EnvironmentMode(str, Enum):
    """Application environment modes."""
    TEST = "test"
    DEV = "dev"
    PROD = "prod"

    @property
    def is_test(self) -> bool:
        return self == self.TEST

    @property
    def is_dev(self) -> bool:
        return self == self.DEV

    @property
    def is_prod(self) -> bool:
        return self == self.PROD

class DatabaseSettings(BaseSettings):
    """Database-specific settings."""
    root_dir: Path = Path("data/db")
    test_db_name: str = "test_yotsu_chat.db"
    dev_db_name: str = "dev_yotsu_chat.db"
    prod_db_name: str = "prod_yotsu_chat.db"

    def get_db_path(self, mode: EnvironmentMode) -> Path:
        """Get the database path for the specified environment mode."""
        db_name = getattr(self, f"{mode.value}_db_name")
        return self.root_dir / mode.value / db_name

    model_config = {
        "env_prefix": "YOTSU_DB_",
        "extra": "ignore"
    }

class JWTSettings(BaseSettings):
    """JWT authentication settings."""
    # Default secrets for development - CHANGE IN PRODUCTION!
    access_token_secret_key: str = "dev-access-secret-key-change-in-production"
    refresh_token_secret_key: str = "dev-refresh-secret-key-change-in-production"
    temp_token_secret_key: str = "dev-temp-secret-key-change-in-production"
    token_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 30
    temp_token_expire_minutes: int = 5

    model_config = {
        "env_prefix": "YOTSU_JWT_",
        "extra": "ignore"
    }

class FileSettings(BaseSettings):
    """File upload and storage settings."""
    max_file_size: int = 20 * 1024 * 1024  # 20MB
    upload_directory: Path = Path("uploads")
    allowed_extensions: set[str] = {"jpg", "jpeg", "png", "gif", "pdf", "doc", "docx"}

    model_config = {
        "env_prefix": "YOTSU_FILE_",
        "extra": "ignore"
    }

class RateLimitSettings(BaseSettings):
    """Rate limiting settings."""
    window_seconds: int = 60
    max_requests: int = 100

    model_config = {
        "env_prefix": "YOTSU_RATE_",
        "extra": "ignore"
    }

class ReactionSettings(BaseSettings):
    """Reaction settings."""
    max_unique_emojis: int = 12

    model_config = {
        "env_prefix": "YOTSU_REACTION_",
        "extra": "ignore"
    }

class Settings(BaseSettings):
    """Main application settings."""
    environment: EnvironmentMode = EnvironmentMode.DEV

    # Nested settings
    db: DatabaseSettings = DatabaseSettings()
    jwt: JWTSettings = JWTSettings()
    file: FileSettings = FileSettings()
    rate_limit: RateLimitSettings = RateLimitSettings()
    reaction: ReactionSettings = ReactionSettings()

    model_config = {
        "env_file": ".env",
        "env_prefix": "YOTSU_",
        "use_enum_values": False,
        "extra": "ignore",
        "json_encoders": {
            EnvironmentMode: lambda v: v.value
        }
    }

    @classmethod
    def parse_environment(cls, value: str) -> EnvironmentMode:
        """Parse environment string to EnvironmentMode enum."""
        try:
            return EnvironmentMode(value.lower())
        except ValueError:
            return EnvironmentMode.DEV

    @property
    def database_url(self) -> str:
        """Get the database URL for the current environment."""
        return str(self.db.get_db_path(self.environment))

    @property
    def is_test_mode(self) -> bool:
        """Check if running in test mode."""
        return self.environment.is_test

    @property
    def is_dev_mode(self) -> bool:
        """Check if running in development mode."""
        return self.environment.is_dev

    @property
    def is_prod_mode(self) -> bool:
        """Check if running in production mode."""
        return self.environment.is_prod

@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings() 