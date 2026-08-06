"""Score/points contract helpers — breakdown must sum to score after clip."""

from __future__ import annotations

from loyalty_abuse.schema import TypologyResult


def reconcile_points(
    rows: list[TypologyResult], score: int
) -> list[TypologyResult]:
    """Scale breakdown points so sum(points) == score (rounding-stable).

    Interaction alphas can push raw > 1 before clip; without reconcile,
    hosts summing typology_breakdown disagree with Decision.score.
    """
    if not rows:
        return rows
    total = sum(int(r.points) for r in rows)
    target = int(score)
    if abs(total - target) <= 1:
        if total == target:
            return rows
        # ±1 rounding: bump/trim largest absolute row
        idx = max(range(len(rows)), key=lambda i: abs(rows[i].points))
        r = rows[idx]
        delta = target - total
        rows = list(rows)
        rows[idx] = TypologyResult(
            id=r.id,
            points=max(0, int(r.points) + delta),
            confidence=r.confidence,
            reasons=list(r.reasons),
        )
        return rows
    if total <= 0:
        return rows
    scale = target / float(total)
    out: list[TypologyResult] = []
    allocated = 0
    for i, r in enumerate(rows):
        if i < len(rows) - 1:
            pts = int(round(int(r.points) * scale))
            allocated += pts
        else:
            pts = max(0, target - allocated)
        out.append(
            TypologyResult(
                id=r.id,
                points=pts,
                confidence=r.confidence,
                reasons=list(r.reasons),
            )
        )
    return out
