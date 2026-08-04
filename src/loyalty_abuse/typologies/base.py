from __future__ import annotations

from typing import Any, Callable

from loyalty_abuse.schema import TypologyResult

Scorer = Callable[[dict[str, Any]], TypologyResult]
