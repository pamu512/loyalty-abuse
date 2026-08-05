"""Pure-Python probability calibration (Platt + histogram binning) and metrics."""

from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Any, Sequence

_PLATT_PATH = Path(__file__).resolve().parent / "calibration" / "platt_v2_0.json"


def _sigmoid(z: float) -> float:
    # Numerically stable logistic.
    if z >= 0.0:
        ez = math.exp(-z)
        return 1.0 / (1.0 + ez)
    ez = math.exp(z)
    return ez / (1.0 + ez)


def predict_platt(score: float, a: float, b: float) -> float:
    """P(abuse) = sigmoid(a * score + b); score typically in [0, 1]."""
    return _sigmoid(float(a) * float(score) + float(b))


def fit_platt(
    scores: list[float],
    labels: list[int],
    *,
    max_iter: int = 100,
    tol: float = 1e-9,
) -> tuple[float, float]:
    """MLE logistic fit for sigmoid(a*s+b). Pure Newton steps; no sklearn."""
    if len(scores) != len(labels):
        raise ValueError("scores and labels length mismatch")
    if not scores:
        raise ValueError("fit_platt requires non-empty scores")
    xs = [float(s) for s in scores]
    ys = [float(int(y)) for y in labels]
    # Prior: mild separation → a>0; intercept near 0.
    a, b = 1.0, 0.0
    for _ in range(max_iter):
        g_a = 0.0
        g_b = 0.0
        h_aa = 0.0
        h_ab = 0.0
        h_bb = 0.0
        for x, y in zip(xs, ys):
            p = _sigmoid(a * x + b)
            # Clip away from 0/1 for Hessian stability.
            p = min(max(p, 1e-15), 1.0 - 1e-15)
            w = p * (1.0 - p)
            d = y - p
            g_a += d * x
            g_b += d
            h_aa += w * x * x
            h_ab += w * x
            h_bb += w
        # Damped Newton on 2x2 Hessian of negative log-likelihood → negate grads.
        # We ascend LL, so step solves H * delta = g with H = -Hessian_LL = observed info.
        det = h_aa * h_bb - h_ab * h_ab
        if abs(det) < 1e-18:
            break
        da = (h_bb * g_a - h_ab * g_b) / det
        db = (h_aa * g_b - h_ab * g_a) / det
        a += da
        b += db
        if abs(da) + abs(db) < tol:
            break
    if not (math.isfinite(a) and math.isfinite(b)):
        raise ValueError("fit_platt diverged")
    return float(a), float(b)


def ece(
    probs: Sequence[float],
    labels: Sequence[int],
    n_bins: int = 10,
) -> float:
    """Expected Calibration Error with equal-width bins on [0, 1]."""
    if len(probs) != len(labels):
        raise ValueError("probs and labels length mismatch")
    n = len(probs)
    if n == 0:
        return 0.0
    if n_bins < 1:
        raise ValueError("n_bins must be >= 1")
    bin_conf = [0.0] * n_bins
    bin_acc = [0.0] * n_bins
    bin_count = [0] * n_bins
    for p, y in zip(probs, labels):
        pf = min(max(float(p), 0.0), 1.0)
        idx = min(int(pf * n_bins), n_bins - 1)
        bin_conf[idx] += pf
        bin_acc[idx] += float(int(y))
        bin_count[idx] += 1
    total = 0.0
    for i in range(n_bins):
        c = bin_count[i]
        if c == 0:
            continue
        avg_conf = bin_conf[i] / c
        avg_acc = bin_acc[i] / c
        total += (c / n) * abs(avg_acc - avg_conf)
    return float(total)


def brier(probs: Sequence[float], labels: Sequence[int]) -> float:
    """Mean squared error between predicted probs and binary labels."""
    if len(probs) != len(labels):
        raise ValueError("probs and labels length mismatch")
    if not probs:
        return 0.0
    s = 0.0
    for p, y in zip(probs, labels):
        d = float(p) - float(int(y))
        s += d * d
    return s / len(probs)


def reliability_bins(
    probs: Sequence[float],
    labels: Sequence[int],
    n_bins: int = 10,
) -> list[dict[str, Any]]:
    """Per-bin counts / mean confidence / empirical accuracy for reporting."""
    if len(probs) != len(labels):
        raise ValueError("probs and labels length mismatch")
    if n_bins < 1:
        raise ValueError("n_bins must be >= 1")
    bin_conf = [0.0] * n_bins
    bin_acc = [0.0] * n_bins
    bin_count = [0] * n_bins
    for p, y in zip(probs, labels):
        pf = min(max(float(p), 0.0), 1.0)
        idx = min(int(pf * n_bins), n_bins - 1)
        bin_conf[idx] += pf
        bin_acc[idx] += float(int(y))
        bin_count[idx] += 1
    out: list[dict[str, Any]] = []
    for i in range(n_bins):
        lo = i / n_bins
        hi = (i + 1) / n_bins
        c = bin_count[i]
        out.append(
            {
                "bin": i,
                "lo": lo,
                "hi": hi,
                "n": c,
                "mean_confidence": (bin_conf[i] / c) if c else None,
                "empirical_accuracy": (bin_acc[i] / c) if c else None,
            }
        )
    return out


# --- Histogram / binning calibrator (isotonic-on-bins fallback; no sklearn) ---

BinEdge = tuple[float, float, float]  # lo, hi, calibrated_p


def fit_binning(
    scores: list[float],
    labels: list[int],
    n_bins: int = 10,
) -> list[BinEdge]:
    """Equal-width histogram binning: each bin → empirical positive rate."""
    if len(scores) != len(labels):
        raise ValueError("scores and labels length mismatch")
    if not scores:
        raise ValueError("fit_binning requires non-empty scores")
    if n_bins < 1:
        raise ValueError("n_bins must be >= 1")
    counts = [0] * n_bins
    pos = [0] * n_bins
    for s, y in zip(scores, labels):
        sf = min(max(float(s), 0.0), 1.0)
        idx = min(int(sf * n_bins), n_bins - 1)
        counts[idx] += 1
        pos[idx] += int(y)
    # Global prior for empty bins.
    prior = sum(int(y) for y in labels) / len(labels)
    edges: list[BinEdge] = []
    for i in range(n_bins):
        lo = i / n_bins
        hi = (i + 1) / n_bins
        p = (pos[i] / counts[i]) if counts[i] else prior
        edges.append((lo, hi, float(p)))
    return edges


def predict_binning(score: float, bins: Sequence[BinEdge]) -> float:
    if not bins:
        raise ValueError("empty binning calibrator")
    sf = min(max(float(score), 0.0), 1.0)
    for lo, hi, p in bins:
        if lo <= sf < hi or (hi >= 1.0 and sf >= lo):
            return float(p)
    return float(bins[-1][2])


@lru_cache(maxsize=1)
def _load_platt_file(path: str) -> dict[str, Any]:
    return json.loads(Path(path).read_text())


def load_platt(path: str | None = None) -> tuple[float, float]:
    data = _load_platt_file(str(path or _PLATT_PATH))
    return float(data["a"]), float(data["b"])


def load_binning(path: str | None = None) -> list[BinEdge] | None:
    """Optional binning block in platt JSON; None if absent."""
    data = _load_platt_file(str(path or _PLATT_PATH))
    raw = data.get("binning")
    if not raw:
        return None
    return [(float(b["lo"]), float(b["hi"]), float(b["p"])) for b in raw]


def predict_calibrated(score_01: float, *, path: str | None = None) -> float:
    """Apply primary calibrator from platt_v2_0.json (platt or binning)."""
    p = str(path or _PLATT_PATH)
    data = _load_platt_file(p)
    method = str(data.get("method") or "platt")
    if method == "binning":
        bins = load_binning(p)
        if bins is None:
            raise ValueError("method=binning but no binning block")
        return predict_binning(score_01, bins)
    return predict_platt(score_01, float(data["a"]), float(data["b"]))


def clear_platt_cache() -> None:
    _load_platt_file.cache_clear()
