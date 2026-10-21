"""Structured JSON logging that cannot leak payment details.

Only an allowlist of fields is ever written, so a careless `extra={"amount": ...}` is dropped
instead of logged. Names, account numbers, amounts, transcripts and audio never appear in logs;
use ids, states, codes and timings.
"""

import json
import logging
import sys
from contextvars import ContextVar
from datetime import UTC, datetime
from typing import Any

request_id_var: ContextVar[str] = ContextVar("request_id", default="-")

# Fields allowed in a log line. Anything else passed via `extra=` is silently dropped.
ALLOWED_FIELDS = frozenset(
    {
        "event", "method", "route", "status", "duration_ms", "code", "state", "from_state",
        "to_state", "request_id_ref", "customer_id", "agent_id", "actor", "error_type", "err",
    }
)  # fmt: skip


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        line: dict[str, Any] = {
            "ts": datetime.now(UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "request_id": request_id_var.get(),
            "msg": record.getMessage(),
        }
        for key in ALLOWED_FIELDS:
            if hasattr(record, key):
                line[key] = getattr(record, key)
        if record.exc_info and record.exc_info[0] is not None:
            line["error_type"] = record.exc_info[0].__name__  # type only: messages can hold data
        return json.dumps(line, separators=(",", ":"), default=str)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
    for noisy in ("uvicorn.access", "uvicorn.error", "sqlalchemy.engine"):
        logging.getLogger(noisy).setLevel(logging.WARNING)  # access lines come from our middleware
