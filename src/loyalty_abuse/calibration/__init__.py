from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_CAL_PATH = Path(__file__).with_name("friction_v3_0.json")


class CalibrationError(ValueError):
    pass


def _validate_interactions(interactions: Any) -> None:
    if not isinstance(interactions, list):
        raise CalibrationError("calibration requires interactions list")
    alpha_sum = 0.0
    for i, row in enumerate(interactions):
        if not isinstance(row, dict):
            raise CalibrationError(f"interactions[{i}] must be an object")
        for key in ("id", "a", "b", "alpha"):
            if key not in row:
                raise CalibrationError(f"interactions[{i}] missing {key}")
        alpha_sum += float(row["alpha"])
    # Catch-power bonus must stay bounded; raw max ≈ 1 + Σα before clip.
    if alpha_sum > 0.35 + 1e-9:
        raise CalibrationError(
            f"interaction alpha sum {alpha_sum} exceeds 0.35 budget"
        )


def _validate_soft_floors(soft_floors: Any) -> None:
    if not isinstance(soft_floors, list):
        raise CalibrationError("calibration requires soft_floors list")


@lru_cache(maxsize=1)
def load_calibration() -> dict[str, Any]:
    data = json.loads(_CAL_PATH.read_text())
    weights = data.get("weights") or {}
    total = sum(float(v) for v in weights.values())
    if abs(total - 1.0) > 1e-6:
        raise CalibrationError(f"weights must sum to 1.0 ± 1e-6, got {total}")
    bands = data.get("bands") or {}
    for key in ("allow_max", "throttle_max", "soft_max", "hard_max"):
        if key not in bands:
            raise CalibrationError(f"bands missing {key}")
    if data.get("blend") != "weighted_sum":
        raise CalibrationError("requires blend=weighted_sum")
    cost = data.get("cost")
    if not isinstance(cost, dict):
        raise CalibrationError("requires cost block")
    for key in ("C_fn_per_usd", "C_fp", "miss_fraction"):
        if key not in cost:
            raise CalibrationError(f"cost missing {key}")
    _validate_interactions(data.get("interactions"))
    _validate_soft_floors(data.get("soft_floors"))
    return data


def sat_params(name: str) -> tuple[float, float]:
    cal = load_calibration()
    pair = (cal.get("sat") or {})[name]
    return float(pair["a"]), float(pair["b"])
