"""Adaptive per-host throttle + circuit breaker for flaky MSTC/GeM portals."""

from __future__ import annotations

import random
import threading
import time
from collections import deque
from dataclasses import dataclass, field

from scraper.config import (
    DOWNLOAD_CIRCUIT_COOLDOWN_SEC,
    DOWNLOAD_CIRCUIT_FAIL_RATIO,
    DOWNLOAD_CIRCUIT_WINDOW,
    DOWNLOAD_THROTTLE_MAX_SEC,
    DOWNLOAD_THROTTLE_MIN_SEC,
)


@dataclass
class HostThrottle:
    host: str
    delay_sec: float = 0.5
    latencies: deque[float] = field(default_factory=lambda: deque(maxlen=30))
    outcomes: deque[bool] = field(default_factory=lambda: deque(maxlen=DOWNLOAD_CIRCUIT_WINDOW))
    circuit_open_until: float = 0.0
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _last_start: float = 0.0

    def wait_turn(self) -> None:
        """Block until polite to hit this host (autothrottle + circuit cool-down)."""
        while True:
            with self._lock:
                now = time.monotonic()
                if now < self.circuit_open_until:
                    sleep_for = self.circuit_open_until - now
                else:
                    gap = max(DOWNLOAD_THROTTLE_MIN_SEC, self.delay_sec)
                    since = now - self._last_start
                    sleep_for = max(0.0, gap - since)
                    if sleep_for <= 0:
                        self._last_start = now
                        return
            time.sleep(min(sleep_for, 5.0) + random.uniform(0, 0.05))

    def record(self, *, ok: bool, latency_sec: float) -> None:
        with self._lock:
            self.outcomes.append(bool(ok))
            if ok and latency_sec > 0:
                self.latencies.append(latency_sec)
                # Scrapy-like: target ~1 concurrent → delay ≈ latency / N (N≈workers hint via avg)
                avg = sum(self.latencies) / len(self.latencies)
                target = avg / 2.0  # allow ~2 in flight per host pacing
                self.delay_sec = min(
                    DOWNLOAD_THROTTLE_MAX_SEC,
                    max(DOWNLOAD_THROTTLE_MIN_SEC, (self.delay_sec + target) / 2.0),
                )
            elif not ok:
                # Non-200 / errors never decrease delay
                self.delay_sec = min(
                    DOWNLOAD_THROTTLE_MAX_SEC,
                    max(self.delay_sec * 1.5, self.delay_sec + 1.0),
                )
            if len(self.outcomes) >= max(5, DOWNLOAD_CIRCUIT_WINDOW // 2):
                fails = sum(1 for x in self.outcomes if not x)
                ratio = fails / len(self.outcomes)
                if ratio >= DOWNLOAD_CIRCUIT_FAIL_RATIO:
                    self.circuit_open_until = time.monotonic() + DOWNLOAD_CIRCUIT_COOLDOWN_SEC
                    self.delay_sec = min(DOWNLOAD_THROTTLE_MAX_SEC, self.delay_sec * 2)
                    self.outcomes.clear()


class DownloadThrottle:
    """Thread-safe registry of per-host throttles."""

    def __init__(self) -> None:
        self._hosts: dict[str, HostThrottle] = {}
        self._lock = threading.Lock()

    def for_host(self, host: str) -> HostThrottle:
        key = (host or "unknown").strip().lower() or "unknown"
        with self._lock:
            if key not in self._hosts:
                self._hosts[key] = HostThrottle(host=key)
            return self._hosts[key]

    def snapshot(self) -> dict[str, dict[str, float | int | bool]]:
        with self._lock:
            out: dict[str, dict[str, float | int | bool]] = {}
            now = time.monotonic()
            for h, t in self._hosts.items():
                with t._lock:
                    out[h] = {
                        "delay_sec": round(t.delay_sec, 3),
                        "circuit_open": now < t.circuit_open_until,
                        "window": len(t.outcomes),
                    }
            return out
