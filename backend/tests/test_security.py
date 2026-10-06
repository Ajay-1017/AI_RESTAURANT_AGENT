"""Unit tests for app/core/security.py. No database needed."""

import uuid
from datetime import UTC, datetime, timedelta

import jwt
import pytest

from app.config import settings
from app.core.security import (
    JWT_ALGORITHM,
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)

# --- Passwords ------------------------------------------------------------------


def test_password_hash_is_argon2id_and_not_plaintext() -> None:
    hashed = hash_password("correct horse battery")

    assert hashed.startswith("$argon2id$")
    assert "correct horse battery" not in hashed


def test_verify_password_accepts_correct_and_rejects_wrong() -> None:
    hashed = hash_password("correct horse battery")

    assert verify_password("correct horse battery", hashed) is True
    assert verify_password("wrong password", hashed) is False


def test_same_password_gets_different_hashes_because_of_salt() -> None:
    assert hash_password("same-password") != hash_password("same-password")


def test_verify_password_with_garbage_hash_returns_false() -> None:
    assert verify_password("anything", "not-a-real-hash") is False


# --- Access tokens --------------------------------------------------------------


def _secret() -> str:
    return settings.jwt_secret_key.get_secret_value()


def test_access_token_round_trip() -> None:
    user_id, session_id = uuid.uuid4(), uuid.uuid4()

    claims = decode_access_token(create_access_token(user_id, session_id))

    assert claims.user_id == user_id
    assert claims.session_id == session_id


def test_expired_access_token_is_rejected() -> None:
    past = datetime.now(UTC) - timedelta(hours=1)
    token = jwt.encode(
        {"sub": str(uuid.uuid4()), "sid": str(uuid.uuid4()), "type": "access",
         "iat": past, "exp": past + timedelta(minutes=15)},
        _secret(),
        algorithm=JWT_ALGORITHM,
    )

    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(token)


def test_token_signed_with_another_secret_is_rejected() -> None:
    now = datetime.now(UTC)
    forged = jwt.encode(
        {"sub": str(uuid.uuid4()), "sid": str(uuid.uuid4()), "type": "access",
         "iat": now, "exp": now + timedelta(minutes=15)},
        "attacker-does-not-know-the-real-secret-1234567890",
        algorithm=JWT_ALGORITHM,
    )

    with pytest.raises(jwt.InvalidSignatureError):
        decode_access_token(forged)


def test_tampered_payload_is_rejected() -> None:
    header, _payload, signature = create_access_token(uuid.uuid4(), uuid.uuid4()).split(".")
    now = datetime.now(UTC)
    other_payload = jwt.encode(
        {"sub": str(uuid.uuid4()), "sid": str(uuid.uuid4()), "type": "access",
         "iat": now, "exp": now + timedelta(minutes=15)},
        "irrelevant-key-only-used-to-build-a-payload-123",
        algorithm=JWT_ALGORITHM,
    ).split(".")[1]

    with pytest.raises(jwt.InvalidSignatureError):
        decode_access_token(f"{header}.{other_payload}.{signature}")


def test_unsigned_alg_none_token_is_rejected() -> None:
    now = datetime.now(UTC)
    unsigned = jwt.encode(
        {"sub": str(uuid.uuid4()), "sid": str(uuid.uuid4()), "type": "access",
         "iat": now, "exp": now + timedelta(minutes=15)},
        key=None,
        algorithm="none",
    )

    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(unsigned)


def test_token_with_wrong_type_is_rejected() -> None:
    now = datetime.now(UTC)
    token = jwt.encode(
        {"sub": str(uuid.uuid4()), "sid": str(uuid.uuid4()), "type": "refresh",
         "iat": now, "exp": now + timedelta(minutes=15)},
        _secret(),
        algorithm=JWT_ALGORITHM,
    )

    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(token)


# --- Refresh tokens -------------------------------------------------------------


def test_refresh_tokens_are_random_and_hash_is_deterministic() -> None:
    token = generate_refresh_token()

    assert token != generate_refresh_token()
    assert hash_refresh_token(token) == hash_refresh_token(token)
    assert len(hash_refresh_token(token)) == 64  # sha256 hex digest
