"""Import every model so Alembic and `Base.metadata` see all tables."""

from zolo.agents.models import Agent
from zolo.audit.models import AuditEvent
from zolo.bank.models import BankAccount, MockAccount, MockTransfer
from zolo.consent.models import PaymentRequest
from zolo.core.base import Base
from zolo.core.models import Customer, SavedRecipient
from zolo.passkeys.models import PasskeyCredential, WebAuthnChallenge
from zolo.phone.models import PhoneCall, PhoneEnrolment
from zolo.risk.models import CardGuardWindow, RiskLimit

__all__ = [
    "Agent",
    "AuditEvent",
    "BankAccount",
    "Base",
    "CardGuardWindow",
    "Customer",
    "MockAccount",
    "MockTransfer",
    "PasskeyCredential",
    "PaymentRequest",
    "PhoneCall",
    "PhoneEnrolment",
    "RiskLimit",
    "SavedRecipient",
    "WebAuthnChallenge",
]
