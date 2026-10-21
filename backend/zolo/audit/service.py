"""The audit trail writer. Append-only, and deliberately unable to record personal data.

`details` may only hold the allowlisted keys below (ids, states, codes). Names, account numbers,
amounts, audio and PINs are refused at write time, so a careless call fails in development
instead of leaking later on the demo projector.
"""

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from zolo.audit.models import AuditEvent

ALLOWED_DETAIL_KEYS = frozenset(
    {
        "state", "from_state", "to_state", "code", "reason", "initiator", "channel", "lang",
        "attempt", "bank_reference", "credential", "field", "changed", "replayed", "ok",
    }
)  # fmt: skip


def _check(details: dict[str, Any]) -> None:
    unknown = set(details) - ALLOWED_DETAIL_KEYS
    if unknown:
        raise ValueError(f"audit details not allowed: {sorted(unknown)}")
    for value in details.values():
        if not isinstance(value, str | int | bool | None):
            raise ValueError("audit detail values must be plain strings, numbers or booleans")


async def record(
    session: AsyncSession,
    event: str,
    actor: str,
    *,
    request_id: uuid.UUID | None = None,
    customer_id: uuid.UUID | None = None,
    **details: Any,
) -> None:
    """Add one event in the caller's transaction (it commits or rolls back with the change)."""
    _check(details)
    session.add(
        AuditEvent(
            request_id=request_id,
            customer_id=customer_id,
            event=event,
            actor=actor,
            details=details,
        )
    )
    await session.flush()
