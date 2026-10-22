"""The customer's recent payments, with a readable line for each (English in Phase 1)."""

import uuid
from dataclasses import dataclass
from datetime import datetime

from zolo.consent.readback import spoken_name


@dataclass(frozen=True)
class ActivityItem:
    id: uuid.UUID
    state: str
    amount_kobo: int
    payee_name: str
    created_at: datetime
    line: str


def naira_text(amount_kobo: int) -> str:
    return f"₦{amount_kobo // 100:,}"


def activity_line(state: str, amount_kobo: int, verified_name: str) -> str:
    amount, who = naira_text(amount_kobo), spoken_name(verified_name)
    match state:
        case "SETTLED":
            return f"Paid {amount} to {who}"
        case "DECLINED":
            return f"You declined {amount} to {who}"
        case "EXPIRED":
            return f"Expired: {amount} to {who}"
        case "FAILED":
            return f"Failed: {amount} to {who}, nothing was sent"
        case _:  # CREATED, READ_BACK, APPROVED, SUBMITTED
            return f"In progress: {amount} to {who}"
