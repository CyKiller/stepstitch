"""Zero-dependency Prometheus metrics for the ingest host.

A tiny in-process registry (request counters + latency sum/count per method+route) and a
Prometheus text-exposition renderer. No external dependency — keeps the host's zero-dep
posture. Labels use the matched **route template** (e.g. ``/session/{trace_id}/summary``),
never the concrete path, so trace ids never become high-cardinality label values.
"""
from __future__ import annotations

import threading
from typing import Dict, Tuple


def _esc(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


class Metrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._requests: Dict[Tuple[str, str, str], int] = {}
        self._lat_sum: Dict[Tuple[str, str], float] = {}
        self._lat_count: Dict[Tuple[str, str], int] = {}

    def observe(self, method: str, route: str, status: int, seconds: float) -> None:
        with self._lock:
            rk = (method, route, str(status))
            self._requests[rk] = self._requests.get(rk, 0) + 1
            lk = (method, route)
            self._lat_sum[lk] = self._lat_sum.get(lk, 0.0) + seconds
            self._lat_count[lk] = self._lat_count.get(lk, 0) + 1

    def render(self) -> str:
        out = []
        with self._lock:
            out.append("# HELP stepstitch_requests_total Total HTTP requests.")
            out.append("# TYPE stepstitch_requests_total counter")
            for (m, r, s), c in sorted(self._requests.items()):
                out.append(
                    f'stepstitch_requests_total{{method="{m}",route="{_esc(r)}",'
                    f'status="{s}"}} {c}'
                )
            out.append("# HELP stepstitch_request_duration_seconds_sum Sum of durations.")
            out.append("# TYPE stepstitch_request_duration_seconds_sum counter")
            for (m, r), v in sorted(self._lat_sum.items()):
                out.append(
                    f'stepstitch_request_duration_seconds_sum{{method="{m}",'
                    f'route="{_esc(r)}"}} {v:.6f}'
                )
            out.append("# HELP stepstitch_request_duration_seconds_count Requests timed.")
            out.append("# TYPE stepstitch_request_duration_seconds_count counter")
            for (m, r), c in sorted(self._lat_count.items()):
                out.append(
                    f'stepstitch_request_duration_seconds_count{{method="{m}",'
                    f'route="{_esc(r)}"}} {c}'
                )
        return "\n".join(out) + "\n"
