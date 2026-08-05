#!/usr/bin/env python3
"""Join stored decisions with challenge outcomes and optional clawbacks into label rows.

Label semantics
---------------
- ``failed`` challenge outcome → ``label_abuse=True``, provenance ``challenge_failed``.
- ``abandoned`` challenge outcome → ``label_abuse=True``, provenance ``challenge_abandoned``.
- ``passed`` challenge outcome → **no row emitted** (not a training label signal; no
  provenance enum value for passed-only outcomes).
- Clawback / ban with abuse label → ``label_abuse=True``, provenance ``clawback``.
- Pre-labeled decisions (``provenance`` in ``red_team`` / ``synth`` with ``label_abuse``)
  are included when no higher-priority signal exists.
- Outcomes or clawbacks referencing unknown ``decision_id`` / ``event_id`` are dropped;
  stored decisions are never mutated or rescored.

Provenance priority (highest wins when multiple signals exist for one decision):
``clawback`` > ``challenge_failed`` > ``challenge_abandoned`` > ``red_team`` > ``synth``.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

PROVENANCE_PRIORITY: dict[str, int] = {
    "clawback": 0,
    "challenge_failed": 1,
    "challenge_abandoned": 2,
    "red_team": 3,
    "synth": 4,
}

_OUTCOME_PROVENANCE: dict[str, tuple[str, bool]] = {
    "failed": ("challenge_failed", True),
    "abandoned": ("challenge_abandoned", True),
}

_ABUSE_LABELS = frozenset({"abuse", "ban", "true", "1", "yes"})
_CLEAN_LABELS = frozenset({"clean", "allow", "false", "0", "no"})


def _load_json(path: Path) -> list[dict[str, Any]]:
    raw = json.loads(path.read_text())
    if not isinstance(raw, list):
        raise ValueError(f"{path}: expected JSON array")
    return raw


def _friction_str(decision: dict[str, Any]) -> str:
    friction = decision.get("friction")
    if friction is None:
        return ""
    if isinstance(friction, str):
        return friction
    if isinstance(friction, dict) and "value" in friction:
        return str(friction["value"])
    return str(friction)


def _parse_label_abuse(row: dict[str, Any]) -> bool | None:
    if "label_abuse" in row:
        return bool(row["label_abuse"])
    label = row.get("label")
    if label is None:
        return None
    text = str(label).strip().lower()
    if text in _ABUSE_LABELS:
        return True
    if text in _CLEAN_LABELS:
        return False
    raise ValueError(f"unrecognized label value: {label!r}")


def _clawback_label(row: dict[str, Any]) -> tuple[str, bool, str] | None:
    label_abuse = _parse_label_abuse(row)
    if label_abuse is None:
        return None
    ts = str(row.get("ts") or "")
    return ("clawback", label_abuse, ts)


def _outcome_label(row: dict[str, Any]) -> tuple[str, bool, str] | None:
    outcome = str(row.get("outcome", "")).strip().lower()
    if outcome == "passed":
        return None
    mapped = _OUTCOME_PROVENANCE.get(outcome)
    if mapped is None:
        raise ValueError(f"unrecognized challenge outcome: {outcome!r}")
    provenance, label_abuse = mapped
    ts = str(row.get("ts") or "")
    return (provenance, label_abuse, ts)


def _decision_embedded_label(row: dict[str, Any]) -> tuple[str, bool, str] | None:
    provenance = row.get("provenance")
    if provenance not in {"red_team", "synth"}:
        return None
    if "label_abuse" not in row:
        return None
    ts = str(row.get("ts") or row.get("created_at") or "")
    return (str(provenance), bool(row["label_abuse"]), ts)


def _pick_label(
    candidates: list[tuple[str, bool, str]],
) -> tuple[str, bool, str] | None:
    if not candidates:
        return None
    return min(candidates, key=lambda c: (PROVENANCE_PRIORITY[c[0]], c[2]))


def build_label_rows(
    decisions: list[dict],
    outcomes: list[dict],
    clawbacks: list[dict] | None = None,
) -> list[dict]:
    """Join decisions with outcomes/clawbacks; apply provenance priority."""
    by_id: dict[str, dict[str, Any]] = {}
    by_event: dict[str, str] = {}
    for d in decisions:
        decision_id = d.get("decision_id")
        if not decision_id:
            continue
        by_id[str(decision_id)] = d
        event_id = d.get("event_id")
        if event_id:
            by_event[str(event_id)] = str(decision_id)

    signals: dict[str, list[tuple[str, bool, str]]] = {did: [] for did in by_id}

    for d in decisions:
        decision_id = str(d["decision_id"])
        embedded = _decision_embedded_label(d)
        if embedded is not None:
            signals[decision_id].append(embedded)

    for outcome in outcomes:
        decision_id = outcome.get("decision_id")
        if decision_id is None:
            continue
        decision_id = str(decision_id)
        if decision_id not in by_id:
            continue
        label = _outcome_label(outcome)
        if label is not None:
            signals[decision_id].append(label)

    for claw in clawbacks or []:
        decision_id = claw.get("decision_id")
        if decision_id is None:
            event_id = claw.get("event_id")
            if event_id is None:
                continue
            decision_id = by_event.get(str(event_id))
            if decision_id is None:
                continue
        else:
            decision_id = str(decision_id)
            if decision_id not in by_id:
                continue
        label = _clawback_label(claw)
        if label is not None:
            signals[decision_id].append(label)

    rows: list[dict[str, Any]] = []
    for decision_id, decision in by_id.items():
        picked = _pick_label(signals.get(decision_id, []))
        if picked is None:
            continue
        provenance, label_abuse, label_ts = picked
        ts = label_ts or str(decision.get("ts") or decision.get("created_at") or "")
        rows.append(
            {
                "decision_id": decision_id,
                "event_id": str(decision.get("event_id") or ""),
                "score": int(decision["score"]),
                "p_abuse": float(decision.get("p_abuse", 0.0)),
                "friction": _friction_str(decision),
                "label_abuse": label_abuse,
                "provenance": provenance,
                "ts": ts,
            }
        )

    rows.sort(key=lambda r: (r["ts"], r["decision_id"]))
    return rows


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--decisions", type=Path, required=True, help="JSON array of decisions")
    p.add_argument("--outcomes", type=Path, required=True, help="JSON array of outcomes")
    p.add_argument("--clawbacks", type=Path, help="Optional JSON array of clawbacks/bans")
    p.add_argument("--out", type=Path, default=Path("artifacts/label_set.json"))
    args = p.parse_args()

    decisions = _load_json(args.decisions)
    outcomes = _load_json(args.outcomes)
    clawbacks = _load_json(args.clawbacks) if args.clawbacks is not None else None

    rows = build_label_rows(decisions, outcomes, clawbacks)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(rows, indent=2) + "\n")
    print(json.dumps({"n": len(rows), "out": str(args.out)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
