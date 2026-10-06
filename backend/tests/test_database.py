import uuid

import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import Engine, inspect, select
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.main import app
from app.models import User
from tests.conftest import _alembic_config


# --- Readiness endpoint -------------------------------------------------------


def test_ready_returns_ok_when_database_reachable(client_with_db: TestClient) -> None:
    response = client_with_db.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "ok"}


class _BrokenSession:
    """Stands in for a Session whose database is down. Needs no real DB."""

    def execute(self, *args, **kwargs):
        raise OperationalError("SELECT 1", {}, Exception("connection refused"))


def test_ready_returns_503_when_database_down() -> None:
    app.dependency_overrides[get_db] = lambda: _BrokenSession()
    try:
        response = TestClient(app).get("/health/ready")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json() == {"detail": "Database unavailable"}  # no internals leaked


# --- User model / constraints -------------------------------------------------


def test_user_gets_uuid_and_database_defaults(db_session: Session) -> None:
    user = User(email="ajay@example.com", hashed_password="not-a-real-hash")
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    assert isinstance(user.id, uuid.UUID)
    assert user.is_active is True
    assert user.created_at.tzinfo is not None  # TIMESTAMPTZ, not naive


def test_email_is_normalized(db_session: Session) -> None:
    db_session.add(User(email="  Ajay@Example.COM ", hashed_password="x"))
    db_session.commit()

    stored = db_session.scalars(select(User.email)).one()
    assert stored == "ajay@example.com"


def test_duplicate_email_is_rejected_by_database(db_session: Session) -> None:
    db_session.add(User(email="dup@example.com", hashed_password="x"))
    db_session.commit()

    # Different case, same address after normalization.
    db_session.add(User(email="DUP@example.com", hashed_password="y"))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()


# --- Migrations ---------------------------------------------------------------


def test_migrations_upgrade_and_downgrade(db_engine: Engine, test_database_url: str) -> None:
    config = _alembic_config(test_database_url)

    command.downgrade(config, "base")
    assert "users" not in inspect(db_engine).get_table_names()

    command.upgrade(config, "head")
    assert "users" in inspect(db_engine).get_table_names()
