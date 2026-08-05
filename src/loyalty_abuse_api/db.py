from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from loyalty_abuse.schema import Decision, EventEnvelope


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
                body_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS shadow_logs (
                decision_id TEXT PRIMARY KEY,
                event_id TEXT NOT NULL,
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
            """
        )
        self._conn.commit()

    def save_event(self, event: EventEnvelope) -> None:
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

    def save_decision(self, decision: Decision) -> None:
        created_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        self._conn.execute(
            """
            INSERT INTO decisions (decision_id, event_id, body_json, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                decision.decision_id,
                decision.event_id,
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

    def list_decisions(self) -> list[Decision]:
        rows = self._conn.execute(
            "SELECT body_json FROM decisions ORDER BY created_at ASC, decision_id ASC"
        ).fetchall()
        return [Decision.model_validate_json(row["body_json"]) for row in rows]

    def save_shadow_log(
        self,
        decision: Decision,
        *,
        host_friction: str | None = None,
    ) -> None:
        created_at = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        self._conn.execute(
            """
            INSERT INTO shadow_logs (
                decision_id, event_id, recommended_friction, host_friction, body_json, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                decision.decision_id,
                decision.event_id,
                decision.friction.value,
                host_friction,
                decision.model_dump_json(),
                created_at,
            ),
        )
        self._conn.commit()

    def list_shadow_logs(self) -> list[dict]:
        rows = self._conn.execute(
            """
            SELECT decision_id, event_id, recommended_friction, host_friction, body_json, created_at
            FROM shadow_logs
            ORDER BY created_at ASC, decision_id ASC
            """
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
