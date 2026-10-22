import uuid
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy.ext.asyncio import AsyncSession

from zolo.core.config import Settings
from zolo.risk.models import RiskLimit
from zolo.risk.rules import Limits


def global_limits(settings: Settings) -> Limits:
    """The hard caps. A request is checked against these before any customer is known."""
    return Limits(settings.per_payment_cap_kobo, settings.daily_cap_kobo)


async def customer_limits(
    session: AsyncSession, customer_id: uuid.UUID, settings: Settings
) -> Limits:
    """The customer's own caps, never above the hard caps (they can lower a cap, not raise it)."""
    hard = global_limits(settings)
    row = await session.get(RiskLimit, customer_id)
    if row is None:
        return hard
    return Limits(
        min(row.per_payment_kobo, hard.per_payment_kobo), min(row.daily_kobo, hard.daily_kobo)
    )


def day_window(now: datetime, tz_name: str) -> tuple[datetime, datetime]:
    """[start, end) of the calendar day containing `now` in the risk timezone (Lagos)."""
    tz = ZoneInfo(tz_name)
    local = now.astimezone(tz)
    start = datetime.combine(local.date(), time.min, tzinfo=tz)
    return start, start + timedelta(days=1)
