"""Label join: decisions + outcomes + clawbacks."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "labels"
sys.path.insert(0, str(ROOT / "scripts"))

from build_label_set import build_label_rows, main  # noqa: E402


def _load(name: str) -> list[dict]:
    return json.loads((FIXTURES / name).read_text())


def test_unknown_decision_id_dropped():
    decisions = _load("decisions.json")
    outcomes = _load("outcomes.json")
    rows = build_label_rows(decisions, outcomes)
    ids = {r["decision_id"] for r in rows}
    assert "dec_unknown" not in ids


def test_failed_challenge_label_abuse_true():
    decisions = _load("decisions.json")
    outcomes = _load("outcomes.json")
    rows = build_label_rows(decisions, outcomes)
    failed = next(r for r in rows if r["decision_id"] == "dec_fail")
    assert failed["label_abuse"] is True
    assert failed["provenance"] == "challenge_failed"
    assert failed["score"] == 72
    assert failed["p_abuse"] == pytest.approx(0.81)
    assert failed["friction"] == "soft_challenge"
    assert failed["ts"] == "2026-08-01T10:30:00Z"


def test_passed_outcome_emits_no_row():
    decisions = _load("decisions.json")
    outcomes = _load("outcomes.json")
    rows = build_label_rows(decisions, outcomes)
    assert all(r["decision_id"] != "dec_pass" for r in rows)


def test_abandoned_outcome_label_abuse_true():
    decisions = _load("decisions.json")
    outcomes = _load("outcomes.json")
    rows = build_label_rows(decisions, outcomes)
    row = next(r for r in rows if r["decision_id"] == "dec_abandon")
    assert row["label_abuse"] is True
    assert row["provenance"] == "challenge_abandoned"


def test_clawback_wins_over_challenge_failed():
    decisions = _load("decisions.json")
    outcomes = _load("outcomes.json")
    clawbacks = _load("clawbacks.json")
    rows = build_label_rows(decisions, outcomes, clawbacks)
    claw = next(r for r in rows if r["decision_id"] == "dec_claw")
    assert claw["provenance"] == "clawback"
    assert claw["label_abuse"] is True
    assert claw["ts"] == "2026-08-02T10:00:00Z"


def test_clawback_priority_over_failed_outcome():
    decisions = _load("decisions.json")
    outcomes = _load("outcomes.json")
    clawbacks = _load("clawbacks.json")
    rows = build_label_rows(decisions, outcomes, clawbacks)
    row = next(r for r in rows if r["decision_id"] == "dec_priority")
    assert row["provenance"] == "clawback"
    assert row["label_abuse"] is True


def test_synth_provenance_from_decision():
    decisions = _load("decisions.json")
    rows = build_label_rows(decisions, outcomes=[])
    synth = next(r for r in rows if r["decision_id"] == "dec_synth")
    assert synth["provenance"] == "synth"
    assert synth["label_abuse"] is False


def test_decisions_not_mutated():
    decisions = _load("decisions.json")
    outcomes = _load("outcomes.json")
    before = json.dumps(decisions)
    build_label_rows(decisions, outcomes)
    assert json.dumps(decisions) == before


def test_cli_writes_output(tmp_path, monkeypatch):
    out = tmp_path / "labels.json"
    monkeypatch.setattr(
        "sys.argv",
        [
            "build_label_set.py",
            "--decisions",
            str(FIXTURES / "decisions.json"),
            "--outcomes",
            str(FIXTURES / "outcomes.json"),
            "--clawbacks",
            str(FIXTURES / "clawbacks.json"),
            "--out",
            str(out),
        ],
    )
    assert main() == 0
    rows = json.loads(out.read_text())
    assert len(rows) >= 4
    assert all(
        set(r) >= {"decision_id", "event_id", "score", "p_abuse", "friction", "label_abuse", "provenance", "ts"}
        for r in rows
    )
