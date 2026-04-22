from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from threading import Lock
from time import time


@dataclass
class MetricsStore:
    started_at: float = field(default_factory=time)
    total_requests: int = 0
    total_errors: int = 0
    latencies_ms: deque[float] = field(default_factory=lambda: deque(maxlen=2000))
    path_counts: dict[str, int] = field(default_factory=dict)
    _lock: Lock = field(default_factory=Lock)

    def record(self, path: str, status_code: int, latency_ms: float) -> None:
        with self._lock:
            self.total_requests += 1
            if status_code >= 500:
                self.total_errors += 1
            self.latencies_ms.append(latency_ms)
            self.path_counts[path] = self.path_counts.get(path, 0) + 1

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            latencies = list(self.latencies_ms)
            uptime = max(1.0, time() - self.started_at)
            total = self.total_requests
            errors = self.total_errors
            path_counts = dict(sorted(self.path_counts.items(), key=lambda x: (-x[1], x[0]))[:20])

        sorted_latencies = sorted(latencies)
        avg = sum(sorted_latencies) / len(sorted_latencies) if sorted_latencies else 0.0
        p95 = 0.0
        if sorted_latencies:
            index = int((len(sorted_latencies) - 1) * 0.95)
            p95 = sorted_latencies[index]

        return {
            "uptime_seconds": round(uptime, 2),
            "requests_total": total,
            "errors_total": errors,
            "qps": round(total / uptime, 4),
            "avg_latency_ms": round(avg, 2),
            "p95_latency_ms": round(p95, 2),
            "error_rate": round(errors / max(1, total), 4),
            "recent_latency_count": len(sorted_latencies),
            "top_paths": path_counts,
        }


metrics_store = MetricsStore()
