"""Outcome-cal path must fail closed without production provenance."""

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "fit_calibration_from_labels.py"


def test_refuses_synth_only_labels(tmp_path: Path):
    labels = tmp_path / "labels.json"
    labels.write_text(
        json.dumps(
            [
                {
                    "decision_id": "d1",
                    "score": 40,
                    "friction": "soft_challenge",
                    "band_friction": "soft_challenge",
                    "label_abuse": True,
                    "provenance": "synth",
                    "ts": "2026-08-01T00:00:00Z",
                }
            ]
        )
        + "\n"
    )
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--labels", str(labels)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 2
    assert "no_production_provenance" in proc.stdout


def test_accepts_challenge_failed_when_enough_rows(tmp_path: Path):
    rows = []
    for i in range(40):
        abuse = i % 3 != 0
        rows.append(
            {
                "decision_id": f"d{i}",
                "score": 70 if abuse else 12,
                "friction": "hard_challenge" if abuse else "allow",
                "band_friction": "hard_challenge" if abuse else "allow",
                "label_abuse": abuse,
                "provenance": "challenge_failed" if abuse else "clawback",
                "ts": f"2026-08-01T00:{i:02d}:00Z",
            }
        )
    labels = tmp_path / "labels.json"
    labels.write_text(json.dumps(rows) + "\n")
    out = tmp_path / "platt.json"
    metrics = tmp_path / "metrics.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--labels",
            str(labels),
            "--out",
            str(out),
            "--metrics-out",
            str(metrics),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode in (0, 1), proc.stdout + proc.stderr
    payload = json.loads(out.read_text())
    assert payload["production_eligible"] is True
    assert payload["method"] == "platt"
