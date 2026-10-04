"""Supabase access-token verification for FastAPI routes."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import jwt
from fastapi import Depends, Header, HTTPException
from jwt import PyJWKClient

from .settings import get_settings


@lru_cache(maxsize=2)
def _jwks_client(url: str) -> PyJWKClient:
    # Supabase's signing-key JWKS is cached for ten minutes, matching its rotation guidance.
    return PyJWKClient(url, cache_jwk_set=True, lifespan=600, timeout=5)


def _verify(token: str) -> dict[str, Any]:
    settings = get_settings()
    issuer = settings.supabase_url + "/auth/v1"
    header = jwt.get_unverified_header(token)
    algorithm = header.get("alg")
    if algorithm == "HS256" and settings.supabase_jwt_secret:
        return jwt.decode(token, settings.supabase_jwt_secret, algorithms=["HS256"], audience="authenticated", issuer=issuer)
    if algorithm not in {"ES256", "RS256"}:
        raise jwt.InvalidTokenError("Unsupported signing algorithm")
    key = _jwks_client(settings.supabase_jwks_url).get_signing_key_from_jwt(token)
    return jwt.decode(token, key.key, algorithms=[algorithm], audience="authenticated", issuer=issuer)


async def require_user(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    settings = get_settings()
    if settings.auth_mode == "demo":
        return {"sub": "local-demo", "role": "demo"}
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="A valid Supabase access token is required.", headers={"WWW-Authenticate": "Bearer"})
    token = authorization[7:].strip()
    if not token:
        raise HTTPException(status_code=401, detail="A valid Supabase access token is required.", headers={"WWW-Authenticate": "Bearer"})
    try:
        return _verify(token)
    except Exception as error:
        raise HTTPException(status_code=401, detail="The Supabase access token is invalid or expired.", headers={"WWW-Authenticate": "Bearer"}) from error


CurrentUser = Depends(require_user)
