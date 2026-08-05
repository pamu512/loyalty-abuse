"""ECE-gated calibration retrain script."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from retrain_calibration import (  # noqa: E402
    build_candidate_payload,
    load_label_rows,
    main,
    retrain_from_rows,
    split_chronological,
)


def _row(
    *,
    decision_id: str,
    ts: str,
    score: int,
    label_abuse: bool,
) -> dict:
    return {
        "decision_id": decision_id,
        "event_id": f"evt_{decision_id}",
        "score": score,
        "p_abuse": score / 100.0,
        "friction": "allow",
        "label_abuse": label_abuse,
        "provenance": "synth",
        "ts": ts,
    }


def _well_calibrated_rows(n_per_bin: int = 40) -> list[dict]:
    rows: list[dict] = []
    i = 0
    for score, label in (
        (10, False),
        (30, False),
        (50, True),
        (70, True),
        (90, True),
    ):
        for j in range(n_per_bin):
            rows.append(
                _row(
                    decision_id=f"good_{i}",
                    ts=f"2026-08-{1 + i // 50:02d}T{(i % 24):02d}:00:00Z",
                    score=score,
                    label_abuse=label,
                )
            )
            i += 1
    return rows


def _bad_report_rows() -> list[dict]:
    """Train is separable; report inverts labels → high held-out ECE."""
    train: list[dict] = []
    for i in range(60):
        label = i % 2 == 0
        score = 90 if label else 10
        train.append(
            _row(
                decision_id=f"train_{i}",
                ts=f"2026-08-01T{i // 10:02d}:{i % 10:02d}:00Z",
                score=score,
                label_abuse=label,
            )
        )
    report: list[dict] = []
    for i in range(40):
        label = i % 2 == 0
        score = 90 if label else 10
        report.append(
            _row(
                decision_id=f"rep_{i}",
                ts=f"2026-08-10T{i // 10:02d}:{i % 10:02d}:00Z",
                score=score,
                label_abuse=not label,
            )
        )
    return train + report


def test_split_chronological_respects_train_end():
    rows = [
        _row(decision_id="a", ts="2026-08-01T00:00:00Z", score=10, label_abuse=False),
        _row(decision_id="b", ts="2026-08-02T00:00:00Z", score=20, label_abuse=False),
        _row(decision_id="c", ts="2026-08-03T00:00:00Z", score=80, label_abuse=True),
    ]
    train, report = split_chronological(rows, train_end="2026-08-02T00:00:00Z")
    assert [r["decision_id"] for r in train] == ["a", "b"]
    assert [r["decision_id"] for r in report] == ["c"]


def test_retrain_good_ece_meets_target():
    rows = _well_calibrated_rows()
    result = retrain_from_rows(rows, train_fraction=0.6, ece_threshold=0.05)
    assert result["meets_ece_target"] is True
    assert result["should_write"] is True
    assert result["report_ece"] <= 0.05


def test_retrain_bad_ece_refuses_write():
    rows = _bad_report_rows()
    result = retrain_from_rows(rows, train_end="2026-08-09T23:59:59Z", ece_threshold=0.05)
    assert result["meets_ece_target"] is False
    assert result["should_write"] is False
    assert result["report_ece"] > 0.05


def test_force_allows_write_and_notes_payload():
    rows = _bad_report_rows()
    result = retrain_from_rows(
        rows, train_end="2026-08-09T23:59:59Z", ece_threshold=0.05, force=True
    )
    assert result["should_write"] is True
    payload = build_candidate_payload(result)
    assert payload["force"] is True
    assert payload["meets_ece_target"] is False
    assert "force_note" in payload


def test_bad_ece_does_not_overwrite_file(tmp_path, monkeypatch):
    labels = tmp_path / "labels.json"
    labels.write_text(json.dumps(_bad_report_rows()) + "\n")
    out = tmp_path / "candidate.json"
    prior = {"version": "platt_v2_0", "a": 1.0, "b": 0.0}
    out.write_text(json.dumps(prior) + "\n")
    artifact = tmp_path / "artifact.json"
    monkeypatch.setattr(
        "sys.argv",
        [
            "retrain_calibration.py",
            "--labels",
            str(labels),
            "--out",
            str(out),
            "--artifact-out",
            str(artifact),
            "--train-end",
            "2026-08-09T23:59:59Z",
        ],
    )
    assert main() == 1
    assert json.loads(out.read_text()) == prior
    art = json.loads(artifact.read_text())
    assert art["wrote_candidate"] is False
    assert art["report_ece"] > 0.05


def test_good_ece_writes_candidate(tmp_path, monkeypatch):
    labels = tmp_path / "labels.json"
    labels.write_text(json.dumps(_well_calibrated_rows()) + "\n")
    out = tmp_path / "candidate.json"
    artifact = tmp_path / "artifact.json"
    monkeypatch.setattr(
        "sys.argv",
        [
            "retrain_calibration.py",
            "--labels",
            str(labels),
            "--out",
            str(out),
            "--artifact-out",
            str(artifact),
            "--train-fraction",
            "0.6",
        ],
    )
    assert main() == 0
    payload = json.loads(out.read_text())
    assert payload["method"] == "platt"
    assert payload["meets_ece_target"] is True
    assert payload["force"] is False
    assert "a" in payload and "b" in payload
    art = json.loads(artifact.read_text())
    assert art["wrote_candidate"] is True


def test_force_writes_with_note(tmp_path, monkeypatch):
    labels = tmp_path / "labels.json"
    labels.write_text(json.dumps(_bad_report_rows()) + "\n")
    out = tmp_path / "candidate.json"
    artifact = tmp_path / "artifact.json"
    monkeypatch.setattr(
        "sys.argv",
        [
            "retrain_calibration.py",
            "--labels",
            str(labels),
            "--out",
            str(out),
            "--artifact-out",
            str(artifact),
            "--train-end",
            "2026-08-09T23:59:59Z",
            "--force",
        ],
    )
    assert main() == 0
    payload = json.loads(out.read_text())
    assert payload["force"] is True
    assert payload["meets_ece_target"] is False
    assert "force_note" in payload
    assert payload["report_ece"] > 0.05


def test_load_label_rows_requires_fields(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps([{"score": 1, "label_abuse": True}]) + "\n")
    with pytest.raises(ValueError, match="ts"):
        load_label_rows(path)
