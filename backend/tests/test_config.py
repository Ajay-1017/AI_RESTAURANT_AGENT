import pytest
from pydantic import ValidationError

from app.config import Settings


def test_settings_read_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_NAME", "Test Agent")
    monkeypatch.setenv("ENVIRONMENT", "test")

    settings = Settings(_env_file=None)  # ignore the developer's real .env

    assert settings.app_name == "Test Agent"
    assert settings.environment == "test"


def test_invalid_environment_fails_fast(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENVIRONMENT", "prod")  # typo: not an allowed value

    with pytest.raises(ValidationError):
        Settings(_env_file=None)
