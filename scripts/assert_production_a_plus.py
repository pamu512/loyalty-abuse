#!/usr/bin/env python3
"""Fail-closed gate for production A+ / A++ claims.

Production A+ requires evidence JSON with live shadow provenance — never synth,
never shadow_four_week_sim. This script refuses MET unless the evidence file
passes schema + provenance checks AND status files agree.

Exit codes:
  0 — status correctly NOT MET, or MET with valid evidence
  1 — MET claimed without valid evidence (theater)
  2 — status/evidence inconsistency
"""

from __future__ import annotations

import argparse
import json
import re
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


def _parse_status_line(text: str) -> tuple[str, str]:
    first = text.strip().splitlines()[0] if text.strip() else ""
    if first.startswith("MET"):
        return "MET", first
    if first.startswith("NOT MET"):
        return "NOT MET", first
    if first.startswith("BLOCKED"):
        return "BLOCKED", first
    return "UNKNOWN", first


def _load_evidence(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text())
    if not isinstance(data, dict):
        raise ValueError("evidence must be a JSON object")
    return data


def validate_production_a_plus_evidence(evidence: dict[str, Any]) -> list[str]:
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

    if evidence.get("claim") != "production_a_plus":
        errors.append("claim must be production_a_plus")

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

    # Date span check
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
    p.add_argument(
        "--status",
        type=Path,
        default=ROOT / "docs" / "compliance" / "production-a-plus.status",
    )
    p.add_argument(
        "--evidence",
        type=Path,
        default=ROOT / "docs" / "compliance" / "production-a-plus.evidence.json",
    )
    p.add_argument(
        "--incognia-status",
        type=Path,
        default=ROOT / "docs" / "compliance" / "incognia-live.status",
    )
    args = p.parse_args()

    status_text = args.status.read_text() if args.status.is_file() else "NOT MET — missing file"
    state, line = _parse_status_line(status_text)

    report: dict[str, Any] = {
        "production_a_plus_status_line": line,
        "parsed_state": state,
        "evidence_path": str(args.evidence),
        "errors": [],
        "may_claim_production_a_plus": False,
    }

    if state == "NOT MET":
        report["may_claim_production_a_plus"] = False
        report["ok"] = True
        report["note"] = "honest: production A+ correctly not claimed"
        print(json.dumps(report, indent=2))
        return 0

    if state != "MET":
        report["errors"].append(f"unrecognized status state: {state}")
        report["ok"] = False
        print(json.dumps(report, indent=2))
        return 2

    # MET claimed — evidence must exist and pass.
    if not args.evidence.is_file():
        report["errors"].append("MET claimed but evidence file missing")
        report["ok"] = False
        print(json.dumps(report, indent=2))
        return 1

    try:
        evidence = _load_evidence(args.evidence)
        errs = validate_production_a_plus_evidence(evidence)
    except Exception as exc:
        errs = [str(exc)]
    report["errors"] = errs
    if errs:
        report["ok"] = False
        report["may_claim_production_a_plus"] = False
        print(json.dumps(report, indent=2))
        return 1

    report["ok"] = True
    report["may_claim_production_a_plus"] = True
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
