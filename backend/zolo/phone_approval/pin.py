
"""Secure PIN utilities for Zolo phone-call approval.

The PIN is a separate Zolo approval PIN, never a bank or card PIN.
Only Argon2 hashes should be persisted.
"""

import re

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError, VerifyMismatchError

ph = PasswordHasher()

WEAK_PINS = {
    "0000",
    "1111",
    "2222",
    "3333",
    "4444",
    "5555",
    "6666",
    "7777",
    "8888",
    "9999",
}


def is_weak_pin(pin: str, phone_e164: str | None = None) -> bool:
    """Return True when a PIN is weak or invalid."""

    # Require exactly four ASCII digits.
    if not isinstance(pin, str) or re.fullmatch(r"[0-9]{4}", pin) is None:
        return True

    # Reject repeated digits.
    if pin in WEAK_PINS:
        return True

    # Reject ascending or descending sequences, such as 1234 or 8765.
    digits = [int(digit) for digit in pin]
    differences = [
        digits[index + 1] - digits[index]
        for index in range(len(digits) - 1)
    ]

    if all(diff == 1 for diff in differences):
        return True

    if all(diff == -1 for diff in differences):
        return True

    # Reject PINs matching the last four digits of the enrolled phone.
    if phone_e164:
        phone_digits = "".join(
            character for character in phone_e164
            if character.isascii() and character.isdigit()
        )

        if len(phone_digits) >= 4 and pin == phone_digits[-4:]:
            return True

    return False


def hash_pin(pin: str) -> str:
    """Hash a syntactically valid four-digit PIN with Argon2."""

    if not isinstance(pin, str) or re.fullmatch(r"[0-9]{4}", pin) is None:
        raise ValueError("PIN must contain exactly four digits.")

    if is_weak_pin(pin):
        raise ValueError("PIN is too weak.")

    return ph.hash(pin)


def verify_pin(pin_hash: str, pin: str) -> bool:
    """Verify a PIN without exposing hashing errors to the caller."""

    if not isinstance(pin, str) or re.fullmatch(r"[0-9]{4}", pin) is None:
        return False

    if not isinstance(pin_hash, str) or not pin_hash:
        return False

    try:
        return ph.verify(pin_hash, pin)
    except (VerifyMismatchError, VerificationError):
        # Wrong PIN or invalid stored hash.
        return False
