"""Drift re-eval CLI wraps adversarial suite."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from drift_reeval import main  # noqa: E402


def test_drift_reeval_writes_artifact_and_exits_on_fail(tmp_path, monkeypatch):
    out = tmp_path / "drift_reeval.json"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "sys.argv",
        ["drift_reeval.py", "--seed", "42", "--out", str(out)],
    )

    with patch("drift_reeval.run_suite") as run_suite:
        run_suite.return_value = {
            "gates_pass": False,
            "gates": {"household_fp": False},
            "seed": 42,
        }
        code = main()
    assert code == 1
    assert out.is_file()
    report = json.loads(out.read_text())
    assert report["gates_pass"] is False


def test_drift_reeval_exit_0_on_pass(tmp_path, monkeypatch):
    out = tmp_path / "drift_reeval.json"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "sys.argv",
        ["drift_reeval.py", "--seed", "7", "--out", str(out)],
    )

    with patch("drift_reeval.run_suite") as run_suite:
        run_suite.return_value = {
            "gates_pass": True,
            "gates": {"household_fp": True},
            "seed": 7,
        }
        code = main()
    assert code == 0
    assert json.loads(out.read_text())["gates_pass"] is True
