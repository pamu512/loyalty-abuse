from __future__ import annotations

from loyalty_abuse.schema import TypologyResult


def interaction_results(
    confidences: dict[str, float], interactions: list[dict]
) -> list[TypologyResult]:
    """Return ix.* TypologyResult rows with points=round(100*alpha*c_a*c_b)."""
    rows: list[TypologyResult] = []
    for ix in interactions:
        ca = float(confidences.get(str(ix["a"])) or 0.0)
        cb = float(confidences.get(str(ix["b"])) or 0.0)
        prod = ca * cb
        alpha = float(ix["alpha"])
        points = int(round(100.0 * alpha * prod))
        rid = str(ix["id"])
        rows.append(
            TypologyResult(
                id=rid,
                points=points,
                confidence=prod,
                reasons=[rid] if points > 0 else [],
            )
        )
    return rows


def blend_raw(
    weights: dict[str, float],
    confidences: dict[str, float],
    interactions: list[dict],
) -> float:
    """Σ w c + Σ α c_a c_b, not clipped."""
    raw = sum(
        float(w) * float(confidences.get(str(tid)) or 0.0)
        for tid, w in weights.items()
    )
    for ix in interactions:
        ca = float(confidences.get(str(ix["a"])) or 0.0)
        cb = float(confidences.get(str(ix["b"])) or 0.0)
        raw += float(ix["alpha"]) * ca * cb
    return raw
