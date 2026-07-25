"""
Auth Service — Pydantic schemas (request/response models).

All request bodies are validated here.
Passwords are never returned in responses.
"""

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from libs.db_models.user_models import UserRole


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------
class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role: UserRole = UserRole.DEVELOPER

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        """Basic password strength — at least one digit and one letter."""
        if not any(c.isdigit() for c in v):
            raise ValueError("Password must contain at least one digit.")
        if not any(c.isalpha() for c in v):
            raise ValueError("Password must contain at least one letter.")
        return v


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1)


class SendOTPRequest(BaseModel):
    phone_number: str = Field(pattern=r"^\+[1-9]\d{6,14}$", description="E.164 format, e.g. +919876543210")


class VerifyOTPRequest(BaseModel):
    phone_number: str
    otp: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class DeviceCodeRequest(BaseModel):
    client_id: str | None = "kynetic-cli"
    scope: str | None = "full"


class DeviceTokenRequest(BaseModel):
    device_code: str = Field(min_length=1)
    grant_type: str = Field(default="urn:ietf:params:oauth:grant-type:device_code")


class DeviceVerifyRequest(BaseModel):
    user_code: str = Field(min_length=8, max_length=10)


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------
class UserResponse(BaseModel):
    id: uuid.UUID
    email: EmailStr
    role: UserRole
    phone_number: str | None
    phone_verified: bool
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int   # seconds until access token expires
    user: UserResponse


class DeviceCodeResponse(BaseModel):
    device_code: str
    user_code: str
    verification_uri: str
    verification_uri_complete: str
    expires_in: int = 600
    interval: int = 5


class CliVersionResponse(BaseModel):
    version: str
    min_supported_version: str
    download_url: str
    release_notes: str


class MessageResponse(BaseModel):
    message: str
    success: bool = True

