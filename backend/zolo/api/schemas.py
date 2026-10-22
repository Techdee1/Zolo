"""Request and response models. FastAPI turns these into the OpenAPI schema the frontend
generates its TypeScript types from, so a change here is a contract change."""

import re
import uuid
from datetime import datetime
from typing import Any, Literal
from urllib.parse import parse_qs, urlparse

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

CLAIM_CODE = re.compile(r"^\d{4}$")


class MockLoginIn(BaseModel):
    phone: str = Field(min_length=8, max_length=20, examples=["+2348011111111"])
    otp: str = Field(min_length=4, max_length=10, examples=["123456"])


class SessionOut(BaseModel):
    role: Literal["customer", "agent"]
    id: uuid.UUID
    display_name: str


class RegisterVerifyIn(BaseModel):
    credential: dict[str, Any] = Field(
        description="The PublicKeyCredential JSON from navigator.credentials.create()"
    )
    device_label: str | None = Field(default=None, max_length=60)


class PasskeyOut(BaseModel):
    id: uuid.UUID
    device_label: str | None
    replaced_previous: bool


class AgentRequestIn(BaseModel):
    # StrictInt: money is an integer. "1500000", 1500000.0 and 1e6 are rejected, not converted.
    amount_kobo: StrictInt = Field(
        gt=0, le=10**12, description="Whole naira, in kobo", examples=[1_500_000]
    )


class AgentRequestOut(BaseModel):
    id: uuid.UUID
    claim_code: str | None = Field(description="Four digits; the agent reads it aloud")
    qr_payload: str
    expires_at: datetime
    payee_name: str


class ClaimIn(BaseModel):
    claim_code: str | None = Field(default=None, pattern=r"^\d{4}$", examples=["4821"])
    qr_payload: str | None = Field(default=None, max_length=300)

    @model_validator(mode="after")
    def _exactly_one(self) -> "ClaimIn":
        if (self.claim_code is None) == (self.qr_payload is None):
            raise ValueError("send either claim_code or qr_payload")
        return self

    def code(self) -> str | None:
        """The 4-digit code, from the field or from the QR payload's ?code= parameter."""
        if self.claim_code is not None:
            return self.claim_code
        try:
            values = parse_qs(urlparse(self.qr_payload or "").query).get("code", [])
        except ValueError:
            return None
        return values[0] if len(values) == 1 and CLAIM_CODE.match(values[0]) else None


class RequestOut(BaseModel):
    id: uuid.UUID
    state: Literal[
        "CREATED", "READ_BACK", "APPROVED", "SUBMITTED", "SETTLED", "DECLINED", "EXPIRED", "FAILED"
    ]
    amount_kobo: int
    payee_name: str
    expires_at: datetime
    claimed: bool
    bank_reference: str | None = None
    failure_reason: str | None = None


class ReadbackOut(BaseModel):
    text: str
    # The language of `text`. It is the language asked for, unless `fallback_from` says otherwise.
    lang: Literal["en", "pcm", "yo", "ha", "ig"]
    # Set (to the language asked for) when it was Yoruba, Hausa or Igbo and there is no recording
    # of this exact sentence: `text` is then the English readback. Null when the language is served.
    fallback_from: Literal["yo", "ha", "ig"] | None = None
    audio_url: str | None = None
    amount_words: str
    payee_name: str
    amount_kobo: int
    expires_at: datetime


class ActivityItemOut(BaseModel):
    id: uuid.UUID
    state: str
    amount_kobo: int
    payee_name: str
    created_at: datetime
    line: str = Field(description="A readable line, e.g. 'Paid ₦15,000 to Bisi Ventures'")


class ActivityOut(BaseModel):
    items: list[ActivityItemOut]


class AssertionIn(BaseModel):
    """The PublicKeyCredential JSON from navigator.credentials.get(), passed through as-is."""

    model_config = ConfigDict(extra="allow")


class TamperIn(BaseModel):
    amount_kobo: StrictInt = Field(
        default=5_100_000, gt=0, le=10**12, description="The new amount (default: N51,000)"
    )


class DemoResetOut(BaseModel):
    customers: int
    agents: int
    accounts: int
    recipients: int


class TimelineEventOut(BaseModel):
    id: int
    at: datetime
    event: str
    actor: str
    details: dict[str, Any] = Field(description="Ids, states and reason codes only")


class TimelineOut(BaseModel):
    request: RequestOut
    events: list[TimelineEventOut]


class PhoneEnrolIn(BaseModel):
    phone: str = Field(pattern=r"^\+[1-9][0-9]{7,14}$", examples=["+2348011111111"])
    pin: str = Field(
        pattern=r"^[0-9]{4}$", description="A four digit Zolo PIN: not a card or bank PIN"
    )
    language: Literal["en", "pcm"] = "en"


class PhoneEnrolmentOut(BaseModel):
    enabled: bool = Field(default=True, description="False while phone approval is switched off")
    enrolled: bool
    language: Literal["en", "pcm"] = "en"
    phone_last4: str = ""
    locked: bool = False
    paused: bool = Field(default=False, description="The number was changed recently")


class PhoneCallIn(BaseModel):
    request_id: uuid.UUID


class PhoneKeysIn(BaseModel):
    digits: str = Field(min_length=1, max_length=4, pattern=r"^[0-9]{1,4}$")


class CallPromptOut(BaseModel):
    key: str
    text: str
    audio_url: str | None = Field(
        default=None, description="A recording; when null the app speaks `text` itself"
    )


class PhoneCallOut(BaseModel):
    call_id: uuid.UUID
    stage: Literal["menu", "pin", "done"]
    expects: Literal["choice", "pin", "none"]
    prompts: list[CallPromptOut]
    done: bool
    outcome: Literal["approved", "declined", "ended"] | None = None
