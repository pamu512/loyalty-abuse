from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loyalty_abuse.schema import Decision, EventEnvelope
from loyalty_abuse_api.auth import generate_api_key, hash_api_key


class Database:
    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS events (
                event_id TEXT PRIMARY KEY,
                tenant_id TEXT NOT NULL,
                ts TEXT NOT NULL,
                body_json TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS decisions (
                decision_id TEXT PRIMARY KEY,
                event_id TEXT NOT NULL,
                tenant_id TEXT,
                body_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS shadow_logs (
                decision_id TEXT PRIMARY KEY,
                event_id TEXT NOT NULL,
                tenant_id TEXT,
                recommended_friction TEXT NOT NULL,
                host_friction TEXT,
                body_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS intel_calls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL,
                vendor TEXT NOT NULL,
                success INTEGER NOT NULL,
                latency_ms INTEGER NOT NULL,
                source TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS challenge_outcomes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                decision_id TEXT NOT NULL,
                event_id TEXT,
                outcome TEXT NOT NULL,
                ts TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS api_keys (
                key_id TEXT PRIMARY KEY,
                key_hash TEXT NOT NULL UNIQUE,
                tenant_id TEXT NOT NULL,
                name TEXT NOT NULL,
                scopes TEXT NOT NULL,
                rpm INTEGER NOT NULL DEFAULT 120,
                created_at TEXT NOT NULL,
                revoked INTEGER NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS tenants (
                tenant_id TEXT PRIMARY KEY,
                evaluation_mode TEXT NOT NULL DEFAULT 'live',
                updated_at TEXT NOT NULL
            );
            """
        )
        self._conn.commit()
        self._migrate_tenant_columns()

    def _migrate_tenant_columns(self) -> None:
        for table, col in (("decisions", "tenant_id"), ("shadow_logs", "tenant_id")):
            cols = {
                r["name"]
                for r in self._conn.execute(f"PRAGMA table_info({table})").fetchall()
            }
            if col not in cols:
                self._conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} TEXT")
        self._conn.commit()

    def ensure_tenant(self, tenant_id: str, *, evaluation_mode: str = "live") -> None:
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        self._conn.execute(
            """
            INSERT INTO tenants (tenant_id, evaluation_mode, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(tenant_id) DO NOTHING
            """,
            (tenant_id, evaluation_mode, now),
        )
        self._conn.commit()

    def get_tenant_mode(self, tenant_id: str) -> str:
        self.ensure_tenant(tenant_id)
        row = self._conn.execute(
            "SELECT evaluation_mode FROM tenants WHERE tenant_id = ?",
            (tenant_id,),
        ).fetchone()
        return str(row["evaluation_mode"]) if row else "live"

    def set_tenant_mode(self, tenant_id: str, mode: str) -> None:
        if mode not in {"shadow", "live"}:
            raise ValueError("evaluation_mode must be shadow or live")
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        self._conn.execute(
            """
            INSERT INTO tenants (tenant_id, evaluation_mode, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(tenant_id) DO UPDATE SET
                evaluation_mode = excluded.evaluation_mode,
                updated_at = excluded.updated_at
            """,
            (tenant_id, mode, now),
        )
        self._conn.commit()

    def create_api_key(
        self,
        *,
        tenant_id: str,
        name: str,
        scopes: list[str] | None = None,
        rpm: int = 120,
    ) -> tuple[str, str]:
        """Returns (raw_key, key_id). Raw key shown once."""
        self.ensure_tenant(tenant_id)
        raw = generate_api_key()
        key_id = "key_" + raw[3:11]
        now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        scope_list = scopes or ["evaluate", "read", "export"]
        self._conn.execute(
            """
            INSERT INTO api_keys (
                key_id, key_hash, tenant_id, name, scopes, rpm, created_at, revoked
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 0)
            """,
            (
                key_id,
                hash_api_key(raw),
                tenant_id,
                name,
                json.dumps(scope_list),
                int(rpm),
                now,
            ),
        )
        self._conn.commit()
        return raw, key_id

    def lookup_api_key(self, raw: str) -> dict[str, Any] | None:
        digest = hash_api_key(raw)
        row = self._conn.execute(
            """
            SELECT key_id, tenant_id, scopes, rpm, revoked
            FROM api_keys WHERE key_hash = ?
            """,
            (digest,),
        ).fetchone()
        if row is None or int(row["revoked"]) != 0:
            return None
        return {
            "key_id": row["key_id"],
            "tenant_id": row["tenant_id"],
            "scopes": frozenset(json.loads(row["scopes"])),
            "rpm": int(row["rpm"]),
        }

    def save_event(self, event: EventEnvelope) -> None:
        self.ensure_tenant(event.tenant_id)
        self._conn.execute(
            """
            INSERT OR REPLACE INTO events (event_id, tenant_id, ts, body_json)
            VALUES (?, ?, ?, ?)
            """,
            (
                event.event_id,
                event.tenant_id,
                event.ts,
                event.model_dump_json(),
            ),
        )
        self._conn.commit()

    def get_event(self, event_id: str) -> EventEnvelope | None:
        row = self._conn.execute(
            "SELECT body_json FROM events WHERE event_id = ?",
            (event_id,),
        ).fetchone()
        if row is None:
            return None
        return EventEnvelope.model_validate_json(row["body_json"])

    def list_tenant_events(
        self,
        tenant_id: str,
        *,
        exclude_event_id: str | None = None,
    ) -> list[EventEnvelope]:
        rows = self._conn.execute(
            """
            SELECT body_json FROM events
            WHERE tenant_id = ?
            ORDER BY ts ASC, event_id ASC
            """,
            (tenant_id,),
        ).fetchall()
        out: list[EventEnvelope] = []
        for row in rows:
            ev = EventEnvelope.model_validate_json(row["body_json"])
            if exclude_event_id is not None and ev.event_id == exclude_event_id:
                continue
            out.append(ev)
        return out

    def save_decision(self, decision: Decision, *, tenant_id: str | None = None) -> None:
        created_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        tid = tenant_id
        if tid is None:
            ev = self.get_event(decision.event_id)
            tid = ev.tenant_id if ev else None
        self._conn.execute(
            """
            INSERT INTO decisions (decision_id, event_id, tenant_id, body_json, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                decision.decision_id,
                decision.event_id,
                tid,
                decision.model_dump_json(),
                created_at,
            ),
        )
        self._conn.commit()

    def get_decision(self, decision_id: str) -> Decision | None:
        row = self._conn.execute(
            "SELECT body_json FROM decisions WHERE decision_id = ?",
            (decision_id,),
        ).fetchone()
        if row is None:
            return None
        return Decision.model_validate_json(row["body_json"])

    def get_decision_tenant(self, decision_id: str) -> str | None:
        row = self._conn.execute(
            "SELECT tenant_id, event_id FROM decisions WHERE decision_id = ?",
            (decision_id,),
        ).fetchone()
        if row is None:
            return None
        if row["tenant_id"]:
            return str(row["tenant_id"])
        ev = self.get_event(str(row["event_id"]))
        return ev.tenant_id if ev else None

    def list_decisions(self, *, tenant_id: str | None = None) -> list[Decision]:
        if tenant_id is None:
            rows = self._conn.execute(
                "SELECT body_json FROM decisions ORDER BY created_at ASC, decision_id ASC"
            ).fetchall()
        else:
            rows = self._conn.execute(
                """
                SELECT body_json FROM decisions
                WHERE tenant_id = ?
                ORDER BY created_at ASC, decision_id ASC
                """,
                (tenant_id,),
            ).fetchall()
        return [Decision.model_validate_json(row["body_json"]) for row in rows]

    def export_decisions_ndjson(
        self,
        *,
        tenant_id: str,
        from_ts: str | None = None,
        to_ts: str | None = None,
    ) -> list[str]:
        rows = self._conn.execute(
            """
            SELECT body_json, created_at FROM decisions
            WHERE tenant_id = ?
            ORDER BY created_at ASC, decision_id ASC
            """,
            (tenant_id,),
        ).fetchall()
        out: list[str] = []
        for row in rows:
            created = str(row["created_at"])
            if from_ts and created < from_ts:
                continue
            if to_ts and created > to_ts:
                continue
            out.append(row["body_json"])
        return out

    def export_shadow_ndjson(
        self,
        *,
        tenant_id: str,
        from_ts: str | None = None,
        to_ts: str | None = None,
    ) -> list[str]:
        rows = self._conn.execute(
            """
            SELECT body_json, created_at FROM shadow_logs
            WHERE tenant_id = ?
            ORDER BY created_at ASC, decision_id ASC
            """,
            (tenant_id,),
        ).fetchall()
        out: list[str] = []
        for row in rows:
            created = str(row["created_at"])
            if from_ts and created < from_ts:
                continue
            if to_ts and created > to_ts:
                continue
            out.append(row["body_json"])
        return out

    def save_shadow_log(
        self,
        decision: Decision,
        *,
        host_friction: str | None = None,
        tenant_id: str | None = None,
    ) -> None:
        created_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        tid = tenant_id
        if tid is None:
            ev = self.get_event(decision.event_id)
            tid = ev.tenant_id if ev else None
        self._conn.execute(
            """
            INSERT INTO shadow_logs (
                decision_id, event_id, tenant_id, recommended_friction, host_friction, body_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                decision.decision_id,
                decision.event_id,
                tid,
                decision.friction.value,
                host_friction,
                decision.model_dump_json(),
                created_at,
            ),
        )
        self._conn.commit()

    def list_shadow_logs(self, *, tenant_id: str | None = None) -> list[dict]:
        if tenant_id is None:
            rows = self._conn.execute(
                """
                SELECT decision_id, event_id, recommended_friction, host_friction, body_json, created_at
                FROM shadow_logs
                ORDER BY created_at ASC, decision_id ASC
                """
            ).fetchall()
        else:
            rows = self._conn.execute(
                """
                SELECT decision_id, event_id, recommended_friction, host_friction, body_json, created_at
                FROM shadow_logs
                WHERE tenant_id = ?
                ORDER BY created_at ASC, decision_id ASC
                """,
                (tenant_id,),
            ).fetchall()
        return [
            {
                "decision_id": row["decision_id"],
                "event_id": row["event_id"],
                "recommended_friction": row["recommended_friction"],
                "host_friction": row["host_friction"],
                "body_json": row["body_json"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def log_intel_call(
        self,
        *,
        event_id: str,
        vendor: str,
        success: bool,
        latency_ms: int,
        source: str | None = None,
    ) -> None:
        created_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        self._conn.execute(
            """
            INSERT INTO intel_calls (
                event_id, vendor, success, latency_ms, source, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                event_id,
                vendor,
                1 if success else 0,
                int(latency_ms),
                source,
                created_at,
            ),
        )
        self._conn.commit()

    def list_intel_calls(self) -> list[dict]:
        rows = self._conn.execute(
            """
            SELECT event_id, vendor, success, latency_ms, source, created_at
            FROM intel_calls
            ORDER BY id ASC
            """
        ).fetchall()
        return [
            {
                "event_id": row["event_id"],
                "vendor": row["vendor"],
                "success": bool(row["success"]),
                "latency_ms": int(row["latency_ms"]),
                "source": row["source"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def save_challenge_outcome(
        self,
        *,
        decision_id: str,
        outcome: str,
        ts: str,
        event_id: str | None = None,
    ) -> dict:
        created_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        cur = self._conn.execute(
            """
            INSERT INTO challenge_outcomes (
                decision_id, event_id, outcome, ts, created_at
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (decision_id, event_id, outcome, ts, created_at),
        )
        self._conn.commit()
        return {
            "id": int(cur.lastrowid),
            "decision_id": decision_id,
            "event_id": event_id,
            "outcome": outcome,
            "ts": ts,
            "created_at": created_at,
        }

    def list_challenge_outcomes(self, *, decision_id: str | None = None) -> list[dict]:
        if decision_id is not None:
            rows = self._conn.execute(
                """
                SELECT id, decision_id, event_id, outcome, ts, created_at
                FROM challenge_outcomes
                WHERE decision_id = ?
                ORDER BY id ASC
                """,
                (decision_id,),
            ).fetchall()
        else:
            rows = self._conn.execute(
                """
                SELECT id, decision_id, event_id, outcome, ts, created_at
                FROM challenge_outcomes
                ORDER BY id ASC
                """
            ).fetchall()
        return [
            {
                "id": int(row["id"]),
                "decision_id": row["decision_id"],
                "event_id": row["event_id"],
                "outcome": row["outcome"],
                "ts": row["ts"],
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def ping_writable(self) -> bool:
        try:
            self._conn.execute("SELECT 1")
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS _ready_probe (id INTEGER PRIMARY KEY)"
            )
            self._conn.commit()
            return True
        except sqlite3.Error:
            return False
