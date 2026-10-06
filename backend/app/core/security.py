"""Cryptographic helpers. Pure functions: no database, no HTTP."""

import hashlib
import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.config import settings

# --- Passwords (Argon2id: slow, salted, memory-hard) ---------------------------

_password_hasher = PasswordHasher()

# Used to spend the same time verifying when the email does not exist,
# so response timing does not reveal which emails are registered.
DUMMY_PASSWORD_HASH = _password_hasher.hash("dummy-password-for-timing-equalization")


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    try:
        return _password_hasher.verify(hashed_password, password)
    except (VerificationError, InvalidHashError):
        return False


def password_needs_rehash(hashed_password: str) -> bool:
    """True if the hash was made with weaker parameters than the current ones."""
    return _password_hasher.check_needs_rehash(hashed_password)


# --- Access tokens (JWT, short-lived) -------------------------------------------

JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_TYPE = "access"


@dataclass(frozen=True)
class AccessTokenClaims:
    user_id: uuid.UUID
    session_id: uuid.UUID


def create_access_token(user_id: uuid.UUID, session_id: uuid.UUID) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "sid": str(session_id),
        "type": ACCESS_TOKEN_TYPE,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret_key.get_secret_value(), algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> AccessTokenClaims:
    """Verify signature + expiry and return the claims.

    Raises jwt.InvalidTokenError (or a subclass) for any invalid token.
    """
    payload = jwt.decode(
        token,
        settings.jwt_secret_key.get_secret_value(),
        algorithms=[JWT_ALGORITHM],  # never let the token choose its own algorithm
        options={"require": ["sub", "sid", "type", "iat", "exp"]},
    )
    if payload["type"] != ACCESS_TOKEN_TYPE:
        raise jwt.InvalidTokenError("Not an access token")
    try:
        return AccessTokenClaims(
            user_id=uuid.UUID(payload["sub"]),
            session_id=uuid.UUID(payload["sid"]),
        )
    except ValueError as exc:
        raise jwt.InvalidTokenError("Malformed token claims") from exc


# --- Refresh tokens (opaque random strings, long-lived) -------------------------


def generate_refresh_token() -> str:
    return secrets.token_urlsafe(32)  # 256 bits of randomness


def hash_refresh_token(token: str) -> str:
    # A fast hash is fine here: the input is random, not a guessable password,
    # and a deterministic hash lets us look the session up by it.
    return hashlib.sha256(token.encode()).hexdigest()
