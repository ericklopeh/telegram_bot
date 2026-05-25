"""Autenticación por token para API v1."""

from __future__ import annotations

import hashlib
import secrets
import time
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from fastapi import Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.platform import ApiToken

_rate_buckets: dict[str, list[float]] = defaultdict(list)


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def generate_token() -> tuple[str, str]:
    raw = secrets.token_urlsafe(32)
    return raw, hash_token(raw)


def _check_rate_limit(token_id: int, limit_per_min: int) -> None:
    key = f"token:{token_id}"
    now = time.time()
    window = 60.0
    hits = _rate_buckets[key]
    _rate_buckets[key] = [t for t in hits if now - t < window]
    if len(_rate_buckets[key]) >= limit_per_min:
        raise HTTPException(status_code=429, detail="Rate limit excedido")
    _rate_buckets[key].append(now)


def resolve_api_token(
    db: Session,
    authorization: str | None,
    x_api_key: str | None,
) -> ApiToken:
    raw = None
    if x_api_key:
        raw = x_api_key.strip()
    elif authorization and authorization.lower().startswith("bearer "):
        raw = authorization[7:].strip()
    if not raw:
        raise HTTPException(status_code=401, detail="Token requerido")

    token_hash = hash_token(raw)
    token = db.scalar(select(ApiToken).where(ApiToken.token_hash == token_hash, ApiToken.is_active.is_(True)))
    if not token:
        raise HTTPException(status_code=401, detail="Token inválido")
    if token.expires_at and token.expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Token expirado")

    limit = token.rate_limit_per_min or get_settings().api_rate_limit_per_min
    _check_rate_limit(token.id, limit)
    token.last_used_at = datetime.now(timezone.utc)
    db.flush()
    return token


def require_scope(token: ApiToken, scope: str) -> None:
    scopes = {s.strip() for s in (token.scopes or "read").split(",") if s.strip()}
    if "admin" in scopes or scope in scopes or "read" in scopes:
        return
    raise HTTPException(status_code=403, detail=f"Scope insuficiente: {scope}")
