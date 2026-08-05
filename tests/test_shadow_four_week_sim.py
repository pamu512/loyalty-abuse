"""Smoke tests for 28-day shadow four-week simulation."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from shadow_four_week_sim import BANNER, run_four_week_sim  # noqa: E402


def test_four_week_sim_emits_artifact(tmp_path):
    out = tmp_path / "shadow_four_week_sim.json"
    report = run_four_week_sim(n=56, seed=42, days=28, out=out)
    assert out.is_file()
    on_disk = json.loads(out.read_text())
    assert on_disk == report
    assert report["days"] == 28
    assert report["weeks"] == 4
    assert "precision" in report
    assert "recall" in report
    assert "insult_proxy" in report
    assert 0.0 <= report["precision"] <= 1.0
    assert 0.0 <= report["recall"] <= 1.0
    assert 0.0 <= report["insult_proxy"] <= 1.0
    assert BANNER in report["banner"]
    assert "NOT PRODUCTION A+" in report["banner"]
    assert len(report["by_week"]) == 4
    assert report["pipeline"]["decisions"] == report["scored"]
    assert report["pipeline"]["label_rows"] >= 0


def test_four_week_sim_cli_exits_zero(tmp_path):
    out = tmp_path / "cli_sim.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts" / "shadow_four_week_sim.py"),
            "--n",
            "56",
            "--out",
            str(out),
        ],
        cwd=ROOT,
        env={**dict(**__import__("os").environ), "PYTHONPATH": f"src:{ROOT / 'scripts'}"},
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert out.is_file()
    assert "NOT PRODUCTION A+" in proc.stdout
