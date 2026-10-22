"""Demo-only memory: the last VALID approval assertion per request, so the demo console can
replay it (and show ALREADY_USED). Exists only when DEMO_MODE=true; cleared by /demo/reset;
lost on restart. Nothing here is a secret: an assertion is useless without a fresh challenge."""

import uuid
from typing import Any


class DemoStore:
    def __init__(self) -> None:
        self._last_assertion: dict[uuid.UUID, dict[str, Any]] = {}

    def remember_assertion(self, request_id: uuid.UUID, assertion: dict[str, Any]) -> None:
        self._last_assertion[request_id] = assertion

    def last_assertion(self, request_id: uuid.UUID) -> dict[str, Any] | None:
        return self._last_assertion.get(request_id)

    def clear(self) -> None:
        self._last_assertion.clear()
