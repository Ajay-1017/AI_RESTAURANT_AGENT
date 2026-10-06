"""Auth endpoints: the HTTP layer (status codes, cookies). Logic lives in services/auth.py."""

from typing import Annotated

from fastapi import APIRouter, Cookie, HTTPException, Response, status

from app.api.cookies import clear_auth_cookies, set_auth_cookies
from app.api.deps import CurrentUser, DbSession
from app.models import User
from app.schemas.auth import LoginRequest, RegisterRequest, UserRead
from app.services import auth as auth_service

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", status_code=status.HTTP_201_CREATED, response_model=UserRead)
def register(body: RegisterRequest, db: DbSession) -> User:
    try:
        return auth_service.register_user(db, body.email, body.password)
    except auth_service.EmailAlreadyRegisteredError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="Email is already registered"
        ) from None


@router.post("/login", response_model=UserRead)
def login(body: LoginRequest, response: Response, db: DbSession) -> User:
    try:
        user = auth_service.authenticate_user(db, body.email, body.password)
    except auth_service.InvalidCredentialsError:
        # Same message whether the email exists or not (no user enumeration).
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password"
        ) from None

    tokens = auth_service.create_session(db, user)
    set_auth_cookies(response, tokens)
    return user


@router.post("/refresh", status_code=status.HTTP_204_NO_CONTENT)
def refresh(
    response: Response,
    db: DbSession,
    refresh_token: Annotated[str | None, Cookie()] = None,
) -> None:
    if not refresh_token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    try:
        tokens = auth_service.rotate_refresh_token(db, refresh_token)
    except auth_service.InvalidRefreshTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated"
        ) from None
    set_auth_cookies(response, tokens)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    response: Response,
    db: DbSession,
    refresh_token: Annotated[str | None, Cookie()] = None,
) -> None:
    # Idempotent: logging out twice, or with no session, still succeeds.
    if refresh_token:
        auth_service.revoke_session_by_refresh_token(db, refresh_token)
    clear_auth_cookies(response)


@router.get("/me", response_model=UserRead)
def me(user: CurrentUser) -> User:
    return user
