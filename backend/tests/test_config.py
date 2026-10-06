import pytest
from pydantic import ValidationError

from app.config import Settings

FAKE_DB_URL = "postgresql+psycopg://user:pass@localhost:5432/fake"


def test_settings_read_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_NAME", "Test Agent")
    monkeypatch.setenv("ENVIRONMENT", "test")
    monkeypatch.setenv("DATABASE_URL", FAKE_DB_URL)

    settings = Settings(_env_file=None)  # ignore the developer's real .env

    assert settings.app_name == "Test Agent"
    assert settings.environment == "test"
    assert settings.database_url == FAKE_DB_URL


def test_invalid_environment_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "prod")  # typo: not an allowed value
    monkeypatch.setenv("DATABASE_URL", FAKE_DB_URL)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_missing_database_url_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)
