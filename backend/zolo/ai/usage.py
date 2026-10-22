"""Provider call counters. Counts only: no content, no identifiers."""

import json
import threading
from datetime import UTC, datetime
from pathlib import Path

_lock = threading.Lock()


def count_call(path: Path, provider: str) -> int:
    """Add one call for today and return today's total for this provider."""
    today = datetime.now(UTC).date().isoformat()
    with _lock:
        try:
            data = json.loads(path.read_text())
        except (OSError, ValueError):
            data = {}
        day = data.setdefault(today, {})
        day[provider] = day.get(provider, 0) + 1
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(data))
        except OSError:
            pass  # a counter must never break a payment flow
        return int(day[provider])
