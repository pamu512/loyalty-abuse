from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_CAL_PATH = Path(__file__).with_name("friction_v2_0.json")


class CalibrationError(ValueError):
    pass


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
        raise CalibrationError("friction_v2_0 requires blend=weighted_sum")
    cost = data.get("cost")
    if not isinstance(cost, dict):
        raise CalibrationError("friction_v2_0 requires cost block")
    for key in ("C_fn_per_usd", "C_fp", "miss_fraction"):
        if key not in cost:
            raise CalibrationError(f"cost missing {key}")
    return data


def sat_params(name: str) -> tuple[float, float]:
    cal = load_calibration()
    pair = (cal.get("sat") or {})[name]
    return float(pair["a"]), float(pair["b"])
