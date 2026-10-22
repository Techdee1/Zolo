"""Request states. The transition rules arrive with the state machine (step 4); the model needs
the names now so the database can refuse an unknown state."""

from enum import StrEnum


class State(StrEnum):
    CREATED = "CREATED"
    READ_BACK = "READ_BACK"
    APPROVED = "APPROVED"
    SUBMITTED = "SUBMITTED"
    SETTLED = "SETTLED"
    DECLINED = "DECLINED"
    EXPIRED = "EXPIRED"
    FAILED = "FAILED"


# States in which a 4-digit claim code is still live (one live code at a time, per the PRD).
LIVE_STATES = (State.CREATED, State.READ_BACK)
