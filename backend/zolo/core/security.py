"""Signed session cookies. The cookie holds who you are (role and id) and a random session id,
signed and time-limited; nothing else, and nothing secret."""

import secrets
import uuid
from dataclasses import dataclass
from typing import Literal

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

COOKIE_NAME = "zolo_session"
Role = Literal["customer", "agent"]


@dataclass(frozen=True)
class Principal:
    role: Role
    id: uuid.UUID
    sid: str  # random per login


class SessionCodec:
    def __init__(self, secret: str, max_age_seconds: int) -> None:
        self._serializer = URLSafeTimedSerializer(secret, salt="zolo.session.v1")
        self.max_age = max_age_seconds

    def dumps(self, role: Role, subject: uuid.UUID) -> str:
        return self._serializer.dumps({"r": role, "i": str(subject), "s": secrets.token_urlsafe(9)})

    def loads(self, token: str | None) -> Principal | None:
        if not token:
            return None
        try:
            data = self._serializer.loads(token, max_age=self.max_age)
            role = data["r"]
            if role not in ("customer", "agent"):
                return None
            return Principal(role, uuid.UUID(data["i"]), str(data["s"]))
        except (BadSignature, SignatureExpired, KeyError, ValueError, TypeError):
            return None
