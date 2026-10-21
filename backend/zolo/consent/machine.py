"""The request state machine. Every change is ONE conditional UPDATE, so two clicks, two phones
or a retry can never approve or pay twice: the second finds zero rows and the caller reports
STATE_CONFLICT.

Only the consent module may import this."""

import uuid
from collections.abc import Mapping, Sequence
from typing import Any

from sqlalchemy import ColumnElement, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from zolo.consent.models import PaymentRequest
from zolo.consent.states import State

ALLOWED: frozenset[tuple[State, State]] = frozenset(
    {
        (State.CREATED, State.READ_BACK),
        (State.CREATED, State.EXPIRED),
        (State.READ_BACK, State.APPROVED),
        (State.READ_BACK, State.DECLINED),
        (State.READ_BACK, State.EXPIRED),
        (State.APPROVED, State.SUBMITTED),
        (State.SUBMITTED, State.SETTLED),
        (State.SUBMITTED, State.FAILED),
    }
)
TERMINAL = frozenset({State.SETTLED, State.DECLINED, State.EXPIRED, State.FAILED})
EXPIRABLE = (State.CREATED, State.READ_BACK)


class IllegalTransition(Exception):
    """A programming error: code asked for a move the machine does not allow."""


def is_allowed(source: State, target: State) -> bool:
    return (source, target) in ALLOWED


async def apply_transition(
    session: AsyncSession,
    request_id: uuid.UUID,
    source: State,
    target: State,
    *,
    guards: Sequence[ColumnElement[bool]] = (),
    values: Mapping[str, Any] | None = None,
) -> PaymentRequest | None:
    """UPDATE ... SET state = :target WHERE id = :id AND state = :source [AND guards] RETURNING *.

    Returns the updated row, or None when no row matched (someone else got there first, or a
    guard such as 'not expired' failed). The caller decides which error that means.

    `populate_existing` matters: without it SQLAlchemy returns the copy already cached in the
    session, with the OLD state, and the caller would act on a stale row.
    """
    if not is_allowed(source, target):
        raise IllegalTransition(f"{source} -> {target}")
    statement = (
        update(PaymentRequest)
        .where(PaymentRequest.id == request_id, PaymentRequest.state == source.value, *guards)
        .values(state=target.value, **(values or {}))
        .returning(PaymentRequest)
        .execution_options(synchronize_session=False, populate_existing=True)
    )
    return (await session.execute(statement)).scalar_one_or_none()


async def reload(session: AsyncSession, request_id: uuid.UUID) -> PaymentRequest | None:
    """Re-read a row from the database, ignoring anything cached in the session."""
    return (
        await session.execute(
            select(PaymentRequest)
            .where(PaymentRequest.id == request_id)
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
