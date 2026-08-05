"""Platt calibration + ECE/Brier unit tests (no sklearn)."""

from __future__ import annotations

import math
import random

from loyalty_abuse.calibrate import (
    brier,
    ece,
    fit_binning,
    fit_platt,
    predict_binning,
    predict_platt,
)


def test_predict_platt_bounds_and_sigmoid():
    assert 0.0 < predict_platt(0.5, a=1.0, b=0.0) < 1.0
    assert abs(predict_platt(0.0, a=1.0, b=0.0) - 0.5) < 1e-9
    assert predict_platt(10.0, a=1.0, b=0.0) > 0.99
    assert predict_platt(-10.0, a=1.0, b=0.0) < 0.01


def test_fit_platt_monotonicity_on_separated_scores():
    scores = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
    labels = [0, 0, 0, 0, 0, 1, 1, 1, 1]
    a, b = fit_platt(scores, labels)
    preds = [predict_platt(s, a, b) for s in scores]
    assert all(preds[i] <= preds[i + 1] + 1e-12 for i in range(len(preds) - 1))
    assert preds[0] < 0.5 < preds[-1]


def test_ece_near_zero_on_well_calibrated_synthetic():
    # Perfect calibration: each bin's mean prob equals empirical positive rate.
    rng = random.Random(0)
    probs: list[float] = []
    labels: list[int] = []
    for p in (0.1, 0.3, 0.5, 0.7, 0.9):
        for _ in range(200):
            probs.append(p)
            labels.append(1 if rng.random() < p else 0)
    assert ece(probs, labels, n_bins=10) < 0.05


def test_brier_perfect_and_worst():
    assert brier([0.0, 1.0], [0, 1]) == 0.0
    assert abs(brier([1.0, 0.0], [0, 1]) - 1.0) < 1e-12


def test_ece_empty_and_mismatched_lengths():
    assert ece([], [], n_bins=10) == 0.0
    try:
        ece([0.1], [0, 1])
        raise AssertionError("expected ValueError")
    except ValueError:
        pass


def test_binning_calibrator_reduces_bias():
    # Overconfident scores: high scores but only half positive.
    scores = [0.1] * 50 + [0.9] * 50
    labels = [0] * 50 + [0] * 25 + [1] * 25
    bins = fit_binning(scores, labels, n_bins=10)
    cal = [predict_binning(s, bins) for s in scores]
    raw = list(scores)
    assert ece(cal, labels, n_bins=10) <= ece(raw, labels, n_bins=10) + 1e-12
    assert abs(predict_binning(0.9, bins) - 0.5) < 0.05
