import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, String, func, true
from sqlalchemy.orm import Mapped, mapped_column, relationship, validates

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.user_session import UserSession


def normalize_email(email: str) -> str:
    """"Ajay@Example.com" and "ajay@example.com" must be the same account,
    otherwise the unique constraint can be bypassed by changing case."""
    return email.strip().lower()


class User(Base):
    __tablename__ = "users"

    # UUID primary key: not guessable/enumerable when exposed in URLs or APIs.
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    # unique=True -> UNIQUE constraint (and its index). The database, not
    # Python code, is what guarantees no two users share an email.
    email: Mapped[str] = mapped_column(String(320), unique=True)

    # Argon2id hash. Never store plaintext passwords.
    hashed_password: Mapped[str] = mapped_column(String(255))

    is_active: Mapped[bool] = mapped_column(default=True, server_default=true())

    # TIMESTAMPTZ, set by the database clock.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # One user -> many sessions. passive_deletes lets the database's
    # ON DELETE CASCADE remove sessions instead of SQLAlchemy loading them first.
    sessions: Mapped[list["UserSession"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )

    @validates("email")
    def validate_email(self, _key: str, email: str) -> str:
        return normalize_email(email)

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r}>"
