"""Shared API test helpers — every TestClient call uses a tenant API key."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from loyalty_abuse_api.app import create_app


def authed_client(
    tmp_path: Path,
    *,
    tenant_id: str = "t",
    db_name: str = "t.db",
    rpm: int = 10_000,
    admin_key: str | None = None,
):
    """Return (app, client, headers, raw_key)."""
    app = create_app(db_path=tmp_path / db_name)
    if admin_key:
        import os

        os.environ["LOYALTY_ABUSE_BOOTSTRAP_ADMIN_KEY"] = admin_key
    raw, _key_id = app.state.db.create_api_key(
        tenant_id=tenant_id, name="test", rpm=rpm
    )
    client = TestClient(app)
    headers = {"Authorization": f"Bearer {raw}"}
    return app, client, headers, raw
