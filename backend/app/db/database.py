from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.config import settings

# One engine per process. It owns the connection pool; creating it does NOT
# open a connection yet (connections are opened lazily on first use).
engine = create_engine(
    settings.database_url,
    pool_pre_ping=True,  # test a pooled connection before use; drops dead ones
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
)


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one Session per request, always closed afterwards."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
