"""Shared FastAPI dependencies."""

from typing import Annotated

import jwt
from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.database import get_db
from app.models import User
from app.services.auth import get_valid_session

DbSession = Annotated[Session, Depends(get_db)]


def _unauthorized() -> HTTPException:
    # Same response for every failure reason: don't tell attackers which check failed.
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")


def get_current_user(
    db: DbSession,
    access_token: Annotated[str | None, Cookie()] = None,
) -> User:
    if not access_token:
        raise _unauthorized()

    # 1. Signature + expiry (cryptography only, no database)
    try:
        claims = decode_access_token(access_token)
    except jwt.InvalidTokenError:
        raise _unauthorized() from None

    # 2. Server-side session still valid? (this is what makes logout instant)
    session = get_valid_session(db, claims.session_id, claims.user_id)
    if session is None:
        raise _unauthorized()

    # 3. Account still active?
    user = session.user
    if not user.is_active:
        raise _unauthorized()
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]
