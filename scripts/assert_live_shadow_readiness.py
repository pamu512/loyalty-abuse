#!/usr/bin/env python3
"""Fail-closed gate for live shadow / production readiness claims.

Requires evidence JSON with live shadow provenance — never synth,
never shadow_four_week_sim. Refuses MET unless evidence passes checks
AND status files agree.

Letter-grade ratings are private (`private/CLAIM_LOCK.md`); this script
only validates operational readiness evidence.

Exit codes:
  0 — status correctly NOT MET, or MET with valid evidence
  1 — MET claimed without valid evidence
  2 — status/evidence inconsistency
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

FORBIDDEN_PROVENANCE = frozenset(
    {
        "synth",
        "synthetic",
        "red_team",
        "shadow_four_week_sim",
        "chronological_synth",
        "adversarial",
    }
)
REQUIRED_PROVENANCE = frozenset(
    {"challenge_failed", "challenge_abandoned", "clawback", "live_ops_confirmed"}
)

DEFAULT_STATUS_CANDIDATES = (
    ROOT / "private" / "live-shadow-readiness.status",
    ROOT / "docs" / "compliance" / "live-shadow-readiness.status",
)
DEFAULT_EVIDENCE_CANDIDATES = (
    ROOT / "private" / "live-shadow-readiness.evidence.json",
    ROOT / "docs" / "compliance" / "live-shadow-readiness.evidence.json",
)


def _parse_status_line(text: str) -> tuple[str, str]:
    first = text.strip().splitlines()[0] if text.strip() else ""
    if first.startswith("MET"):
        return "MET", first
    if first.startswith("NOT MET"):
        return "NOT MET", first
    if first.startswith("BLOCKED"):
        return "BLOCKED", first
    return "UNKNOWN", first


def _first_existing(paths: tuple[Path, ...]) -> Path | None:
    for p in paths:
        if p.is_file():
            return p
    return None


def _load_evidence(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        raise ValueError("evidence must be a JSON object")
    return data


def validate_live_shadow_evidence(evidence: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for key in (
        "claim",
        "policy_version",
        "shadow_start",
        "shadow_end",
        "n_shadow_days",
        "n_labeled_outcomes",
        "label_provenance_counts",
        "calibration_ece",
        "calibration_artifact",
        "attestation",
    ):
        if key not in evidence:
            errors.append(f"missing field: {key}")

    if evidence.get("claim") != "live_shadow_readiness":
        errors.append("claim must be live_shadow_readiness")

    try:
        days = int(evidence.get("n_shadow_days") or 0)
        if days < 28:
            errors.append(f"n_shadow_days={days} < 28")
    except (TypeError, ValueError):
        errors.append("n_shadow_days not an int")

    try:
        n_lab = int(evidence.get("n_labeled_outcomes") or 0)
        if n_lab < 50:
            errors.append(f"n_labeled_outcomes={n_lab} < 50")
    except (TypeError, ValueError):
        errors.append("n_labeled_outcomes not an int")

    prov = evidence.get("label_provenance_counts")
    if not isinstance(prov, dict) or not prov:
        errors.append("label_provenance_counts must be non-empty object")
    else:
        keys = {str(k) for k in prov}
        if keys & FORBIDDEN_PROVENANCE:
            errors.append(f"forbidden provenance present: {sorted(keys & FORBIDDEN_PROVENANCE)}")
        if not (keys & REQUIRED_PROVENANCE):
            errors.append(
                "need at least one of challenge_failed|challenge_abandoned|clawback|live_ops_confirmed"
            )
        if any(str(k).startswith("synth") or "sim" in str(k) for k in keys):
            errors.append("synth/sim provenance keys forbidden")

    try:
        ece = float(evidence.get("calibration_ece"))
        if ece > 0.05:
            errors.append(f"calibration_ece={ece} > 0.05 (production target)")
    except (TypeError, ValueError):
        errors.append("calibration_ece not a float")

    att = evidence.get("attestation")
    if not isinstance(att, dict):
        errors.append("attestation must be object")
    else:
        if att.get("not_simulation") is not True:
            errors.append("attestation.not_simulation must be true")
        if att.get("live_traffic") is not True:
            errors.append("attestation.live_traffic must be true")
        if not att.get("operator"):
            errors.append("attestation.operator required")

    try:
        start = datetime.fromisoformat(str(evidence["shadow_start"]).replace("Z", "+00:00"))
        end = datetime.fromisoformat(str(evidence["shadow_end"]).replace("Z", "+00:00"))
        span = (end - start).total_seconds() / 86400.0
        if span < 27.0:
            errors.append(f"shadow date span {span:.1f}d < 27d")
        if end > datetime.now(timezone.utc):
            errors.append("shadow_end is in the future")
    except Exception as exc:
        errors.append(f"shadow_start/end parse error: {exc}")

    return errors


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--status", type=Path, default=None)
    p.add_argument("--evidence", type=Path, default=None)
    args = p.parse_args()

    status_path = args.status or _first_existing(DEFAULT_STATUS_CANDIDATES)
    evidence_path = args.evidence or _first_existing(DEFAULT_EVIDENCE_CANDIDATES)

    if status_path is None:
        status_text = "NOT MET — missing status file (ratings private; see private/README.md)"
        status_path = DEFAULT_STATUS_CANDIDATES[0]
    else:
        status_text = status_path.read_text()

    state, line = _parse_status_line(status_text)

    report: dict[str, Any] = {
        "status_path": str(status_path),
        "status_line": line,
        "parsed_state": state,
        "evidence_path": str(evidence_path) if evidence_path else None,
        "errors": [],
        "may_claim_live_shadow_readiness": False,
    }

    if state == "NOT MET":
        report["may_claim_live_shadow_readiness"] = False
        report["ok"] = True
        report["note"] = "honest: live shadow readiness correctly not claimed"
        print(json.dumps(report, indent=2))
        return 0

    if state != "MET":
        report["errors"].append(f"unrecognized status state: {state}")
        report["ok"] = False
        print(json.dumps(report, indent=2))
        return 2

    if evidence_path is None or not evidence_path.is_file():
        report["errors"].append("MET claimed but evidence file missing")
        report["ok"] = False
        print(json.dumps(report, indent=2))
        return 1

    try:
        evidence = _load_evidence(evidence_path)
        errs = validate_live_shadow_evidence(evidence)
    except Exception as exc:
        errs = [str(exc)]
    report["errors"] = errs
    if errs:
        report["ok"] = False
        report["may_claim_live_shadow_readiness"] = False
        print(json.dumps(report, indent=2))
        return 1

    report["ok"] = True
    report["may_claim_live_shadow_readiness"] = True
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
