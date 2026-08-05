from __future__ import annotations


def clip(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, float(x)))


def sat(x: float, a: float, b: float) -> float:
    """Saturating map: 0 at x<=a, 1 at x>=b, linear between."""
    if b <= a:
        raise ValueError(f"sat requires b > a, got a={a}, b={b}")
    return clip((float(x) - float(a)) / (float(b) - float(a)))
