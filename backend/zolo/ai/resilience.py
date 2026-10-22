"""Circuit breaker: a provider is switched off for 60 seconds after 3 failures in a row."""

import time
from collections.abc import Callable


class CircuitBreaker:
    def __init__(
        self,
        threshold: int = 3,
        cooldown_s: float = 60.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.threshold = threshold
        self.cooldown_s = cooldown_s
        self._clock = clock
        self._failures = 0
        self._open_until = 0.0

    @property
    def is_open(self) -> bool:
        return self._clock() < self._open_until

    def record_success(self) -> None:
        self._failures = 0

    def record_failure(self) -> None:
        self._failures += 1
        if self._failures >= self.threshold:
            self._open_until = self._clock() + self.cooldown_s
            self._failures = 0
