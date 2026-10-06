"""Authentication business logic: users and server-side sessions.

Knows about the database, not about HTTP (no cookies, no status codes).
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.core.security import (
    DUMMY_PASSWORD_HASH,
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    password_needs_rehash,
    verify_password,
)
from app.models import User, UserSession
from app.models.user import normalize_email


class EmailAlreadyRegisteredError(Exception):
    pass


class InvalidCredentialsError(Exception):
    pass


class InvalidRefreshTokenError(Exception):
    pass


@dataclass(frozen=True)
class IssuedTokens:
    access_token: str
    refresh_token: str


def register_user(db: Session, email: str, password: str) -> User:
    user = User(email=email, hashed_password=hash_password(password))
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        # No "SELECT first" check: the UNIQUE constraint is the source of truth,
        # and it also wins the race when two registrations arrive together.
        db.rollback()
        raise EmailAlreadyRegisteredError from None
    db.refresh(user)
    return user


def authenticate_user(db: Session, email: str, password: str) -> User:
    user = db.scalar(select(User).where(User.email == normalize_email(email)))

    if user is None:
        verify_password(password, DUMMY_PASSWORD_HASH)  # equalize response time
        raise InvalidCredentialsError
    if not verify_password(password, user.hashed_password) or not user.is_active:
        raise InvalidCredentialsError

    if password_needs_rehash(user.hashed_password):
        # Hashing parameters were strengthened since this hash was made.
        # Saved together with the new session in create_session().
        user.hashed_password = hash_password(password)
    return user


def create_session(db: Session, user: User) -> IssuedTokens:
    refresh_token = generate_refresh_token()
    session = UserSession(
        user_id=user.id,
        refresh_token_hash=hash_refresh_token(refresh_token),
        expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days),
    )
    db.add(session)
    db.flush()  # INSERT now so session.id is assigned before we sign it into the JWT
    access_token = create_access_token(user.id, session.id)
    db.commit()
    return IssuedTokens(access_token=access_token, refresh_token=refresh_token)


def rotate_refresh_token(db: Session, refresh_token: str) -> IssuedTokens:
    session = db.scalar(
        select(UserSession)
        .where(UserSession.refresh_token_hash == hash_refresh_token(refresh_token))
        # Row lock: two concurrent refreshes with the same token cannot both succeed.
        .with_for_update()
    )
    if session is None or not session.is_valid(datetime.now(UTC)) or not session.user.is_active:
        db.rollback()  # release the lock
        raise InvalidRefreshTokenError

    new_refresh_token = generate_refresh_token()
    session.refresh_token_hash = hash_refresh_token(new_refresh_token)  # old token dies here
    access_token = create_access_token(session.user_id, session.id)
    db.commit()
    return IssuedTokens(access_token=access_token, refresh_token=new_refresh_token)


def revoke_session_by_refresh_token(db: Session, refresh_token: str) -> None:
    session = db.scalar(
        select(UserSession).where(
            UserSession.refresh_token_hash == hash_refresh_token(refresh_token)
        )
    )
    if session is not None and session.revoked_at is None:
        session.revoked_at = datetime.now(UTC)
        db.commit()


def get_valid_session(db: Session, session_id: uuid.UUID, user_id: uuid.UUID) -> UserSession | None:
    session = db.get(UserSession, session_id)
    if session is None or session.user_id != user_id or not session.is_valid(datetime.now(UTC)):
        return None
    return session
