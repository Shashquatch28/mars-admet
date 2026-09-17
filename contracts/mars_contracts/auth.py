"""
M3 contract — Module 13 auth flow, pinned to concrete request/response shapes.
Session strategy is server-side Redis sessions (opaque token in an HttpOnly
cookie), NOT JWT — the response bodies below never carry a token; it travels
only via Set-Cookie/Cookie headers (see `API_ROUTES.md`).

Changing field names here is a breaking change and requires a re-sync.
"""

from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)
    turnstile_token: str = Field(..., description="Cloudflare Turnstile response token (Module 8 registration gate)")


class RegisterResponse(BaseModel):
    user_id: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class LoginResponse(BaseModel):
    user_id: str
    # session token itself is set via HttpOnly Set-Cookie, never in the body


class PasswordResetRequestModel(BaseModel):
    email: EmailStr


class PasswordResetConfirmRequest(BaseModel):
    token: str
    new_password: str = Field(..., min_length=8)


__all__ = [
    "RegisterRequest",
    "RegisterResponse",
    "LoginRequest",
    "LoginResponse",
    "PasswordResetRequestModel",
    "PasswordResetConfirmRequest",
]
