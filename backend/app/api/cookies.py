"""Auth cookie names and flags, in one place."""

from fastapi import Response

from app.config import settings
from app.services.auth import IssuedTokens

ACCESS_TOKEN_COOKIE = "access_token"
REFRESH_TOKEN_COOKIE = "refresh_token"

# The long-lived refresh token is only sent to /auth/* (refresh, logout),
# not with every API request.
REFRESH_TOKEN_PATH = "/auth"


def set_auth_cookies(response: Response, tokens: IssuedTokens) -> None:
    response.set_cookie(
        ACCESS_TOKEN_COOKIE,
        tokens.access_token,
        max_age=settings.access_token_expire_minutes * 60,
        path="/",
        httponly=True,  # invisible to JavaScript -> not stealable via XSS
        secure=settings.cookie_secure,  # HTTPS only (in production)
        samesite="lax",  # not sent on cross-site POSTs -> CSRF protection
    )
    response.set_cookie(
        REFRESH_TOKEN_COOKIE,
        tokens.refresh_token,
        max_age=settings.refresh_token_expire_days * 24 * 60 * 60,
        path=REFRESH_TOKEN_PATH,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )


def clear_auth_cookies(response: Response) -> None:
    # A cookie is only deleted if name AND path match how it was set.
    response.delete_cookie(
        ACCESS_TOKEN_COOKIE, path="/", httponly=True, secure=settings.cookie_secure, samesite="lax"
    )
    response.delete_cookie(
        REFRESH_TOKEN_COOKIE,
        path=REFRESH_TOKEN_PATH,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
    )
