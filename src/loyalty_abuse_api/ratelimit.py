"""In-process token-bucket rate limiter per API key."""

from __future__ import annotations

import threading
import time


class RateLimitExceeded(Exception):
    def __init__(self, retry_after: float) -> None:
        super().__init__("rate limit exceeded")
        self.retry_after = max(1.0, float(retry_after))


class RateLimiter:
    """Token bucket: ``rpm`` refill rate, burst = rpm (one minute of tokens)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._buckets: dict[str, tuple[float, float]] = {}  # key_id -> (tokens, last_ts)

    def check(self, key_id: str, rpm: int) -> None:
        rpm = max(1, int(rpm))
        now = time.monotonic()
        with self._lock:
            tokens, last = self._buckets.get(key_id, (float(rpm), now))
            elapsed = max(0.0, now - last)
            tokens = min(float(rpm), tokens + elapsed * (rpm / 60.0))
            if tokens < 1.0:
                need = 1.0 - tokens
                retry = need / (rpm / 60.0)
                self._buckets[key_id] = (tokens, now)
                raise RateLimitExceeded(retry)
            self._buckets[key_id] = (tokens - 1.0, now)
