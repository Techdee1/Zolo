"""The Zolo approval PIN: four digits, salted and slow-hashed with scrypt (standard library), so
no extra dependency. Brute force is stopped by the lockout, not by the hash."""

import hashlib
import hmac
import os
import re

_PIN = re.compile(r"^[0-9]{4}$")
_N, _R, _P = 2**14, 8, 1
_SALT = 16


def is_valid_format(pin: str) -> bool:
    return bool(_PIN.fullmatch(pin))


def is_weak(pin: str, phone_e164: str = "") -> bool:
    """Repeated digits, straight runs (1234, 4321) and the last four digits of the phone number."""
    if not is_valid_format(pin):
        return True
    digits = [int(c) for c in pin]
    steps = {digits[i + 1] - digits[i] for i in range(3)}
    if len(set(pin)) == 1 or steps in ({1}, {-1}):
        return True
    return bool(phone_e164) and pin == re.sub(r"\D", "", phone_e164)[-4:]


def _derive(pin: str, salt: bytes) -> bytes:
    return hashlib.scrypt(pin.encode(), salt=salt, n=_N, r=_R, p=_P, dklen=32)


def hash_pin(pin: str) -> bytes:
    salt = os.urandom(_SALT)
    return salt + _derive(pin, salt)


def verify_pin(stored: bytes, pin: str) -> bool:
    if not is_valid_format(pin) or len(stored) != _SALT + 32:
        return False
    return hmac.compare_digest(stored[_SALT:], _derive(pin, stored[:_SALT]))
