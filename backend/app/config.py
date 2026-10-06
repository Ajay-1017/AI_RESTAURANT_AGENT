from typing import Literal, Self

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration, read from environment variables (and .env).

    Field names map to env vars case-insensitively: `app_name` <- APP_NAME.
    Values are type-checked at startup, so bad config fails fast.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",  # unrelated keys in .env should not crash the app
    )

    app_name: str = "AI Restaurant Agent"
    app_version: str = "0.1.0"
    environment: Literal["development", "test", "production"] = "development"

    # Required: the app refuses to start without a database URL.
    database_url: str

    # Separate database used only by pytest. Tests that need it are
    # skipped when it is not set.
    test_database_url: str | None = None

    # --- Authentication ---
    # SecretStr hides the value in repr/logs: str(settings.jwt_secret_key) -> '**********'.
    jwt_secret_key: SecretStr = Field(min_length=32)
    access_token_expire_minutes: int = Field(default=15, gt=0)
    refresh_token_expire_days: int = Field(default=7, gt=0)
    # Secure cookies are only sent over HTTPS. Off for http://localhost in dev.
    cookie_secure: bool = False

    @model_validator(mode="after")
    def require_secure_cookies_in_production(self) -> Self:
        if self.environment == "production" and not self.cookie_secure:
            raise ValueError("COOKIE_SECURE must be true in production")
        return self


settings = Settings()
