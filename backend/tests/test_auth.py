"""End-to-end auth flows through the HTTP API, against the test database."""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import User, UserSession

EMAIL = "ajay@example.com"
PASSWORD = "correct horse battery"


def register(client: TestClient, email: str = EMAIL, password: str = PASSWORD):
    return client.post("/auth/register", json={"email": email, "password": password})


def login(client: TestClient, email: str = EMAIL, password: str = PASSWORD):
    return client.post("/auth/login", json={"email": email, "password": password})


def set_cookie_headers(response) -> list[str]:
    return response.headers.get_list("set-cookie")


# --- Registration ---------------------------------------------------------------


def test_register_creates_user_with_hashed_password(
    client_with_db: TestClient, db_session: Session
) -> None:
    response = register(client_with_db)

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == EMAIL
    assert "hashed_password" not in body and "password" not in body

    stored = db_session.scalars(select(User)).one()
    assert stored.hashed_password.startswith("$argon2id$")


def test_register_duplicate_email_returns_409(client_with_db: TestClient) -> None:
    register(client_with_db)

    response = register(client_with_db, email="AJAY@example.com")  # same after normalization

    assert response.status_code == 409


def test_register_validates_input(client_with_db: TestClient) -> None:
    assert register(client_with_db, password="short").status_code == 422
    assert register(client_with_db, email="not-an-email").status_code == 422
    assert register(client_with_db, password="x" * 129).status_code == 422

    extra_field = client_with_db.post(
        "/auth/register", json={"email": EMAIL, "password": PASSWORD, "is_superuser": True}
    )
    assert extra_field.status_code == 422


# --- Login ----------------------------------------------------------------------


def test_login_sets_httponly_cookies(client_with_db: TestClient) -> None:
    register(client_with_db)

    response = login(client_with_db)

    assert response.status_code == 200
    assert response.json()["email"] == EMAIL
    cookies = set_cookie_headers(response)
    access = next(c for c in cookies if c.startswith("access_token="))
    refresh = next(c for c in cookies if c.startswith("refresh_token="))
    for cookie in (access, refresh):
        assert "HttpOnly" in cookie
        assert "samesite=lax" in cookie.lower()
    assert "Path=/;" in access or access.endswith("Path=/")
    assert "Path=/auth" in refresh
    # Tokens travel only in cookies, never in the JSON body.
    assert "access_token" not in response.json()


def test_login_failure_messages_are_identical(client_with_db: TestClient) -> None:
    register(client_with_db)

    wrong_password = login(client_with_db, password="wrong password")
    unknown_email = login(client_with_db, email="nobody@example.com")

    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()


def test_login_creates_server_side_session(
    client_with_db: TestClient, db_session: Session
) -> None:
    register(client_with_db)
    login(client_with_db)

    session = db_session.scalars(select(UserSession)).one()
    refresh_cookie = client_with_db.cookies.get("refresh_token")
    assert session.revoked_at is None
    assert session.refresh_token_hash != refresh_cookie  # only the hash is stored


# --- Protected endpoint ---------------------------------------------------------


def test_me_requires_authentication(client_with_db: TestClient) -> None:
    assert client_with_db.get("/auth/me").status_code == 401


def test_me_returns_current_user_after_login(client_with_db: TestClient) -> None:
    register(client_with_db)
    login(client_with_db)

    response = client_with_db.get("/auth/me")

    assert response.status_code == 200
    assert response.json()["email"] == EMAIL


def test_me_rejects_garbage_token(client_with_db: TestClient) -> None:
    client_with_db.cookies.set("access_token", "not.a.jwt")

    assert client_with_db.get("/auth/me").status_code == 401


# --- Refresh --------------------------------------------------------------------


def test_refresh_rotates_tokens_and_old_refresh_token_stops_working(
    client_with_db: TestClient,
) -> None:
    register(client_with_db)
    login(client_with_db)
    old_refresh = client_with_db.cookies.get("refresh_token")

    response = client_with_db.post("/auth/refresh")

    assert response.status_code == 204
    new_refresh = client_with_db.cookies.get("refresh_token")
    assert new_refresh != old_refresh
    assert client_with_db.get("/auth/me").status_code == 200  # new access token works

    # An attacker replaying the old refresh token is rejected.
    client_with_db.cookies.clear()
    client_with_db.cookies.set("refresh_token", old_refresh)
    assert client_with_db.post("/auth/refresh").status_code == 401

    # Control: the same mechanism with the *current* token succeeds, proving the
    # 401 above came from rotation and not from the cookie failing to be sent.
    client_with_db.cookies.clear()
    client_with_db.cookies.set("refresh_token", new_refresh)
    assert client_with_db.post("/auth/refresh").status_code == 204


def test_refresh_without_cookie_returns_401(client_with_db: TestClient) -> None:
    assert client_with_db.post("/auth/refresh").status_code == 401


def test_refresh_rejected_after_session_expires(
    client_with_db: TestClient, db_session: Session
) -> None:
    register(client_with_db)
    login(client_with_db)
    session = db_session.scalars(select(UserSession)).one()
    session.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    db_session.commit()

    assert client_with_db.post("/auth/refresh").status_code == 401
    assert client_with_db.get("/auth/me").status_code == 401


# --- Logout / revocation --------------------------------------------------------


def test_logout_revokes_session_immediately(
    client_with_db: TestClient, db_session: Session
) -> None:
    register(client_with_db)
    login(client_with_db)
    stolen_access_token = client_with_db.cookies.get("access_token")
    # Control: a manually set access cookie is accepted while the session is live.
    client_with_db.cookies.set("access_token", stolen_access_token)
    assert client_with_db.get("/auth/me").status_code == 200

    response = client_with_db.post("/auth/logout")

    assert response.status_code == 204
    assert db_session.scalars(select(UserSession)).one().revoked_at is not None

    # The JWT has not expired, but the session check rejects it.
    client_with_db.cookies.set("access_token", stolen_access_token)
    assert client_with_db.get("/auth/me").status_code == 401


def test_logout_without_session_is_idempotent(client_with_db: TestClient) -> None:
    assert client_with_db.post("/auth/logout").status_code == 204


def test_deactivated_user_is_rejected_immediately(
    client_with_db: TestClient, db_session: Session
) -> None:
    register(client_with_db)
    login(client_with_db)
    user = db_session.scalars(select(User)).one()
    user.is_active = False
    db_session.commit()

    assert client_with_db.get("/auth/me").status_code == 401
    assert client_with_db.post("/auth/refresh").status_code == 401
    assert login(client_with_db).status_code == 401
