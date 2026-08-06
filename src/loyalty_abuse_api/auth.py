"""API key principals — SHA-256 hashed secrets, tenant-bound."""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from dataclasses import dataclass


def hash_api_key(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def generate_api_key() -> str:
    return "la_" + secrets.token_urlsafe(32)


def bootstrap_admin_key() -> str | None:
    raw = os.environ.get("LOYALTY_ABUSE_BOOTSTRAP_ADMIN_KEY", "").strip()
    return raw or None


@dataclass(frozen=True)
class ApiPrincipal:
    key_id: str
    tenant_id: str
    scopes: frozenset[str]
    rpm: int
    is_admin: bool = False

    def has_scope(self, scope: str) -> bool:
        return self.is_admin or scope in self.scopes or "admin" in self.scopes


def parse_bearer(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.strip().split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    token = parts[1].strip()
    return token or None


def constant_time_equal(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))
