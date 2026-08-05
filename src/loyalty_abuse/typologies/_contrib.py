from __future__ import annotations

from loyalty_abuse.calibration import load_calibration
from loyalty_abuse.schema import TypologyResult


def result(typology_id: str, confidence: float, reasons: list[str]) -> TypologyResult:
    cal = load_calibration()
    w = float((cal.get("weights") or {}).get(typology_id) or 0.0)
    c = max(0.0, min(1.0, float(confidence)))
    points = int(round(100.0 * w * c))
    return TypologyResult(
        id=typology_id,
        points=points,
        confidence=c,
        reasons=reasons if c > 0 else [],
    )
