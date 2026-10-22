"""Risk rules: plain functions over a request and recent history. Each returns allow, pause
(needs an extra check) or block, with a reason code the app can speak. Values are config.

Phase 1 has the two hard caps only. Pause rules (new payee, velocity, late night) are Phase 2.
"""

from dataclasses import dataclass
from enum import StrEnum


class Verdict(StrEnum):
    ALLOW = "ALLOW"
    PAUSE = "PAUSE"
    BLOCK = "BLOCK"


@dataclass(frozen=True)
class Limits:
    per_payment_kobo: int
    daily_kobo: int


@dataclass(frozen=True)
class Decision:
    verdict: Verdict
    code: str = ""  # PER_PAYMENT_CAP or DAILY_CAP when not allowed

    @property
    def allowed(self) -> bool:
        return self.verdict is Verdict.ALLOW


ALLOW = Decision(Verdict.ALLOW)


def check_per_payment(amount_kobo: int, limits: Limits) -> Decision:
    if amount_kobo > limits.per_payment_kobo:
        return Decision(Verdict.BLOCK, "PER_PAYMENT_CAP")
    return ALLOW


def check_daily(amount_kobo: int, already_today_kobo: int, limits: Limits) -> Decision:
    if already_today_kobo + amount_kobo > limits.daily_kobo:
        return Decision(Verdict.BLOCK, "DAILY_CAP")
    return ALLOW


def evaluate(amount_kobo: int, already_today_kobo: int, limits: Limits) -> Decision:
    """All Phase 1 rules, in order; the first that is not ALLOW wins."""
    for decision in (
        check_per_payment(amount_kobo, limits),
        check_daily(amount_kobo, already_today_kobo, limits),
    ):
        if not decision.allowed:
            return decision
    return ALLOW
