"""Domain errors that carry an HTTP status and a stable code (RFC 9457 `code`).

They live in `core` so modules such as `consent` can raise them without importing the API layer.
The API layer turns them into problem+json responses.
"""

from enum import StrEnum


class ErrorCode(StrEnum):
    # listed in the Backend PRD
    LIMIT_EXCEEDED = "LIMIT_EXCEEDED"
    CODE_NOT_FOUND = "CODE_NOT_FOUND"
    REQUEST_EXPIRED = "REQUEST_EXPIRED"
    STATE_CONFLICT = "STATE_CONFLICT"
    INTENT_CHANGED = "INTENT_CHANGED"
    SIGNATURE_INVALID = "SIGNATURE_INVALID"
    ALREADY_USED = "ALREADY_USED"
    # needed around them
    UNAUTHENTICATED = "UNAUTHENTICATED"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    VALIDATION_ERROR = "VALIDATION_ERROR"
    RATE_LIMITED = "RATE_LIMITED"
    NAME_ENQUIRY_FAILED = "NAME_ENQUIRY_FAILED"
    NO_PASSKEY = "NO_PASSKEY"
    PASSKEY_REGISTRATION_FAILED = "PASSKEY_REGISTRATION_FAILED"
    CHALLENGE_NOT_FOUND = "CHALLENGE_NOT_FOUND"
    RISK_BLOCKED = "RISK_BLOCKED"
    BANK_REJECTED = "BANK_REJECTED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


class ApiError(Exception):
    def __init__(
        self,
        status: int,
        code: ErrorCode,
        title: str,
        detail: str = "",
        retry_after: int | None = None,
    ) -> None:
        super().__init__(f"{code}: {title}")
        self.status, self.code, self.title, self.detail = status, code, title, detail
        self.retry_after = retry_after  # seconds, sent as a Retry-After header on 429
