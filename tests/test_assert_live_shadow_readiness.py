"""Fail-closed live shadow readiness gate (ratings stay private)."""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "assert_live_shadow_readiness.py"


def test_current_repo_not_met_is_ok():
    proc = subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    report = json.loads(proc.stdout)
    assert report["may_claim_live_shadow_readiness"] is False
    assert report["ok"] is True


def test_met_without_evidence_fails(tmp_path: Path):
    status = tmp_path / "live-shadow-readiness.status"
    status.write_text("MET — forged\n")
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--status",
            str(status),
            "--evidence",
            str(tmp_path / "missing.json"),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1
    report = json.loads(proc.stdout)
    assert report["ok"] is False


def test_met_with_synth_provenance_fails(tmp_path: Path):
    status = tmp_path / "live-shadow-readiness.status"
    status.write_text("MET — should fail\n")
    evidence = tmp_path / "ev.json"
    evidence.write_text(
        json.dumps(
            {
                "claim": "live_shadow_readiness",
                "policy_version": "friction_v3_0",
                "shadow_start": "2026-01-01T00:00:00Z",
                "shadow_end": "2026-02-01T00:00:00Z",
                "n_shadow_days": 31,
                "n_labeled_outcomes": 100,
                "label_provenance_counts": {"synth": 100},
                "calibration_ece": 0.01,
                "calibration_artifact": "x.json",
                "attestation": {
                    "not_simulation": True,
                    "live_traffic": True,
                    "operator": "test",
                },
            }
        )
    )
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--status",
            str(status),
            "--evidence",
            str(evidence),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 1
    assert "forbidden provenance" in proc.stdout


def test_met_with_valid_live_evidence_ok(tmp_path: Path):
    status = tmp_path / "live-shadow-readiness.status"
    status.write_text("MET — live shadow complete\n")
    evidence = tmp_path / "ev.json"
    evidence.write_text(
        json.dumps(
            {
                "claim": "live_shadow_readiness",
                "policy_version": "friction_v3_0",
                "shadow_start": "2026-01-01T00:00:00Z",
                "shadow_end": "2026-02-01T00:00:00Z",
                "n_shadow_days": 31,
                "n_labeled_outcomes": 100,
                "label_provenance_counts": {
                    "challenge_failed": 40,
                    "clawback": 60,
                },
                "calibration_ece": 0.04,
                "calibration_artifact": "artifacts/platt_from_outcomes.json",
                "attestation": {
                    "not_simulation": True,
                    "live_traffic": True,
                    "operator": "ops@example.com",
                },
            }
        )
    )
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--status",
            str(status),
            "--evidence",
            str(evidence),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    report = json.loads(proc.stdout)
    assert report["may_claim_live_shadow_readiness"] is True
    assert report["ok"] is True
