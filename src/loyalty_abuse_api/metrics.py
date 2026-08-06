"""Minimal Prometheus text exposition — no extra dependency."""

from __future__ import annotations

import threading
import time
from collections import defaultdict


class MetricsRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.requests_total: dict[tuple[str, str], int] = defaultdict(int)
        self.friction_total: dict[str, int] = defaultdict(int)
        self.evaluate_latency_ms: list[float] = []
        self.errors_total: dict[str, int] = defaultdict(int)

    def observe_request(self, method: str, status: int) -> None:
        with self._lock:
            self.requests_total[(method, str(status))] += 1
            if status >= 400:
                self.errors_total[str(status)] += 1

    def observe_friction(self, friction: str) -> None:
        with self._lock:
            self.friction_total[friction] += 1

    def observe_evaluate_latency(self, ms: float) -> None:
        with self._lock:
            self.evaluate_latency_ms.append(float(ms))
            if len(self.evaluate_latency_ms) > 5000:
                self.evaluate_latency_ms = self.evaluate_latency_ms[-2500:]

    def render(self) -> str:
        lines: list[str] = [
            "# HELP loyalty_abuse_requests_total HTTP requests",
            "# TYPE loyalty_abuse_requests_total counter",
        ]
        with self._lock:
            for (method, status), n in sorted(self.requests_total.items()):
                lines.append(
                    f'loyalty_abuse_requests_total{{method="{method}",status="{status}"}} {n}'
                )
            lines.append("# HELP loyalty_abuse_friction_total Decisions by friction")
            lines.append("# TYPE loyalty_abuse_friction_total counter")
            for fr, n in sorted(self.friction_total.items()):
                lines.append(f'loyalty_abuse_friction_total{{friction="{fr}"}} {n}')
            lines.append("# HELP loyalty_abuse_errors_total HTTP errors by status")
            lines.append("# TYPE loyalty_abuse_errors_total counter")
            for status, n in sorted(self.errors_total.items()):
                lines.append(f'loyalty_abuse_errors_total{{status="{status}"}} {n}')
            lat = list(self.evaluate_latency_ms)
        if lat:
            avg = sum(lat) / len(lat)
            lines.append("# HELP loyalty_abuse_evaluate_latency_ms_avg Evaluate latency")
            lines.append("# TYPE loyalty_abuse_evaluate_latency_ms_avg gauge")
            lines.append(f"loyalty_abuse_evaluate_latency_ms_avg {avg:.3f}")
            lines.append("# HELP loyalty_abuse_evaluate_latency_count Samples")
            lines.append("# TYPE loyalty_abuse_evaluate_latency_count counter")
            lines.append(f"loyalty_abuse_evaluate_latency_count {len(lat)}")
        lines.append(f"# scrapetime {time.time():.0f}")
        return "\n".join(lines) + "\n"


METRICS = MetricsRegistry()
