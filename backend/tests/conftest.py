from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session

from app.config import settings
from app.db.database import get_db
from app.main import app

ALEMBIC_INI = Path(__file__).resolve().parents[1] / "alembic.ini"


def _alembic_config(url: str) -> Config:
    config = Config(str(ALEMBIC_INI))
    config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    return config


@pytest.fixture(scope="session")
def test_database_url() -> str:
    url = settings.test_database_url
    if not url:
        pytest.skip("TEST_DATABASE_URL is not set; skipping database tests")
    if url == settings.database_url:
        pytest.exit("TEST_DATABASE_URL must differ from DATABASE_URL (tests drop tables)")
    return url


@pytest.fixture(scope="session")
def db_engine(test_database_url: str) -> Iterator[Engine]:
    # Build the schema the same way production does: through migrations.
    command.upgrade(_alembic_config(test_database_url), "head")
    engine = create_engine(test_database_url)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(db_engine: Engine) -> Iterator[Session]:
    """A Session whose work is rolled back after each test.

    The outer transaction is never committed. Inside it, session.commit()
    only releases a SAVEPOINT, so tests can commit/rollback normally and
    still leave the database clean.
    """
    connection = db_engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def client_with_db(db_session: Session) -> Iterator[TestClient]:
    """TestClient whose routes use the test database session."""
    app.dependency_overrides[get_db] = lambda: db_session
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
