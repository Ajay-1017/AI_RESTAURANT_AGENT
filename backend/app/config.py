from typing import Literal

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


settings = Settings()
