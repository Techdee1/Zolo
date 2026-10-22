"""In-memory rate limiting: a sliding window per (bucket, key), and a lock after repeated
failures. One process only (fine for the demo); a shared store replaces it for several workers.

The window counts attempts, so a flood is slowed even when every attempt would have succeeded.
"""

import time
from collections import defaultdict, deque
from collections.abc import Callable

from zolo.core.errors import ApiError, ErrorCode


def _limited(retry_after: float) -> ApiError:
    seconds = max(1, int(retry_after + 0.999))
    return ApiError(
        429, ErrorCode.RATE_LIMITED, "Too many attempts, try again shortly", retry_after=seconds
    )


class RateLimiter:
    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)
        self._failures: dict[tuple[str, str], int] = defaultdict(int)
        self._locked_until: dict[tuple[str, str], float] = {}

    def check(self, bucket: str, key: str, limit: int, window_s: float = 60.0) -> None:
        """Record one attempt; raise 429 if there were already `limit` in the last window."""
        now = self._clock()
        hits = self._hits[(bucket, key)]
        while hits and now - hits[0] >= window_s:
            hits.popleft()
        if len(hits) >= limit:
            raise _limited(window_s - (now - hits[0]))
        hits.append(now)

    def assert_unlocked(self, bucket: str, key: str) -> None:
        until = self._locked_until.get((bucket, key))
        if until is not None:
            now = self._clock()
            if now < until:
                raise _limited(until - now)
            del self._locked_until[(bucket, key)]
            self._failures[(bucket, key)] = 0

    def fail(self, bucket: str, key: str, *, max_failures: int, lock_seconds: float) -> None:
        """Record a wrong attempt. The Nth one locks the key for `lock_seconds`."""
        self._failures[(bucket, key)] += 1
        if self._failures[(bucket, key)] >= max_failures:
            self._locked_until[(bucket, key)] = self._clock() + lock_seconds

    def succeed(self, bucket: str, key: str) -> None:
        self._failures[(bucket, key)] = 0

    def clear(self) -> None:
        """Forget everything (the demo reset uses this so a rehearsal cannot lock the stage)."""
        self._hits.clear()
        self._failures.clear()
        self._locked_until.clear()
