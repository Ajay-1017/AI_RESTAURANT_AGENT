import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.user import User


class UserSession(Base):
    """A server-side login session, one per device/login.

    Named UserSession (not Session) to avoid confusion with SQLAlchemy's Session.
    """

    __tablename__ = "user_sessions"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    # Foreign key: the database rejects sessions for non-existent users, and
    # ON DELETE CASCADE removes a user's sessions when the user is deleted.
    # index=True because PostgreSQL does not index foreign keys automatically.
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )

    # SHA-256 hex digest of the refresh token. The raw token is never stored.
    refresh_token_hash: Mapped[str] = mapped_column(String(64), unique=True)

    # Absolute expiry: refreshing does not extend it; after this, log in again.
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))

    # NULL while active; set on logout. Kept (not deleted) as an audit trail.
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    user: Mapped["User"] = relationship(back_populates="sessions")

    def is_valid(self, now: datetime) -> bool:
        return self.revoked_at is None and self.expires_at > now

    def __repr__(self) -> str:
        return f"<UserSession id={self.id} user_id={self.user_id}>"
