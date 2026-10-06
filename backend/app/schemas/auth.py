"""Request/response shapes for the auth API (validation happens here)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class RegisterRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")  # reject unexpected fields

    email: EmailStr
    # Upper bound stops huge inputs from burning CPU in Argon2.
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class UserRead(BaseModel):
    """Public view of a user. hashed_password is deliberately absent."""

    model_config = ConfigDict(from_attributes=True)  # build from a SQLAlchemy object

    id: uuid.UUID
    email: str
    is_active: bool
    created_at: datetime
