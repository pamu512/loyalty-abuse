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


def test_failed_wins_over_abandoned_on_same_decision():
    decisions = [
        {
            "decision_id": "dec_both",
            "event_id": "evt_both",
            "score": 40,
            "p_abuse": 0.4,
            "friction": "soft_challenge",
            "ts": "2026-08-01T00:00:00Z",
        }
    ]
    outcomes = [
        {"decision_id": "dec_both", "outcome": "abandoned", "ts": "2026-08-01T01:00:00Z"},
        {"decision_id": "dec_both", "outcome": "failed", "ts": "2026-08-01T02:00:00Z"},
    ]
    rows = build_label_rows(decisions, outcomes)
    assert len(rows) == 1
    assert rows[0]["provenance"] == "challenge_failed"
    assert rows[0]["label_abuse"] is True


def test_unknown_clawback_decision_id_dropped():
    decisions = _load("decisions.json")
    clawbacks = [
        {"decision_id": "dec_missing", "label": "abuse", "ts": "2026-08-04T00:00:00Z"},
        {"event_id": "evt_does_not_exist", "label": "abuse", "ts": "2026-08-04T00:00:00Z"},
    ]
    rows = build_label_rows(decisions, outcomes=[], clawbacks=clawbacks)
    ids = {r["decision_id"] for r in rows}
    assert "dec_missing" not in ids
    assert all(r.get("event_id") != "evt_does_not_exist" for r in rows)


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
