import pytest
from pydantic import ValidationError

from app.config import Settings

FAKE_DB_URL = "postgresql+psycopg://user:pass@localhost:5432/fake"
FAKE_JWT_SECRET = "x" * 32


@pytest.fixture
def required_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    """Set the minimum required variables; tests then change one thing."""
    monkeypatch.setenv("DATABASE_URL", FAKE_DB_URL)
    monkeypatch.setenv("JWT_SECRET_KEY", FAKE_JWT_SECRET)
    return monkeypatch


def test_settings_read_from_environment(required_env: pytest.MonkeyPatch) -> None:
    required_env.setenv("APP_NAME", "Test Agent")
    required_env.setenv("ENVIRONMENT", "test")

    settings = Settings(_env_file=None)  # ignore the developer's real .env

    assert settings.app_name == "Test Agent"
    assert settings.environment == "test"
    assert settings.database_url == FAKE_DB_URL


def test_invalid_environment_fails_fast(required_env: pytest.MonkeyPatch) -> None:
    required_env.setenv("ENVIRONMENT", "prod")  # typo: not an allowed value

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_missing_database_url_fails_fast(required_env: pytest.MonkeyPatch) -> None:
    required_env.delenv("DATABASE_URL")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_short_jwt_secret_fails_fast(required_env: pytest.MonkeyPatch) -> None:
    required_env.setenv("JWT_SECRET_KEY", "too-short")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_jwt_secret_is_hidden_in_repr(required_env: pytest.MonkeyPatch) -> None:
    settings = Settings(_env_file=None)

    assert FAKE_JWT_SECRET not in repr(settings)


def test_production_requires_secure_cookies(required_env: pytest.MonkeyPatch) -> None:
    required_env.setenv("ENVIRONMENT", "production")
    required_env.setenv("COOKIE_SECURE", "false")

    with pytest.raises(ValidationError, match="COOKIE_SECURE"):
        Settings(_env_file=None)
