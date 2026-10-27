from __future__ import annotations

import time
from typing import Any

import jwt
from jwt import PyJWTError

from app.core.config import get_settings


class JwtVerificationError(Exception):
    pass


def verify_supabase_jwt(token: str) -> dict[str, Any]:
    settings = get_settings()
    if not settings.supabase_jwt_secret:
        raise JwtVerificationError("SUPABASE_JWT_SECRET is not configured")
    options = {"verify_aud": bool(settings.jwt_audience)}
    decode_kwargs: dict[str, Any] = {
        "jwt": token,
        "key": settings.supabase_jwt_secret,
        "algorithms": ["HS256"],
        "options": options,
    }
    if settings.jwt_audience:
        decode_kwargs["audience"] = settings.jwt_audience
    if settings.jwt_issuer:
        decode_kwargs["issuer"] = settings.jwt_issuer
    try:
        return jwt.decode(**decode_kwargs)
    except PyJWTError as exc:
        raise JwtVerificationError(str(exc)) from exc


def claims_to_user(claims: dict[str, Any]) -> dict[str, Any]:
    # Only app_metadata is server-controlled in Supabase. user_metadata is
    # writable by the signed-in user (auth.updateUser), so a role found there
    # must never be honoured -- otherwise anyone could make themselves admin.
    role = "user"
    app_metadata = claims.get("app_metadata") or {}
    if isinstance(app_metadata, dict) and app_metadata.get("role"):
        role = str(app_metadata["role"])
    return {
        "id": str(claims.get("sub", "")),
        "email": claims.get("email"),
        "role": role,
    }
