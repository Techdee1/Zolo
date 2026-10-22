"""Spoken bank names -> canonical keys. Shared by recipient matching and the grammar."""

import re
import unicodedata

# canonical key -> spoken variants (normalised: lowercase, no punctuation)
_BANKS: dict[str, tuple[str, ...]] = {
    "opay": ("opay", "o pay", "opay digital"),
    "gtbank": ("gtbank", "gtb", "gt bank", "guaranty trust", "guaranty trust bank", "gt"),
    "zenith": ("zenith", "zenith bank"),
    "access": ("access", "access bank"),
    "uba": ("uba", "united bank for africa"),
    "firstbank": ("first bank", "firstbank", "fbn"),
    "kuda": ("kuda", "kuda bank"),
    "palmpay": ("palmpay", "palm pay"),
    "moniepoint": ("moniepoint", "monie point"),
    "wema": ("wema", "wema bank", "alat"),
    "sterling": ("sterling", "sterling bank"),
    "fcmb": ("fcmb", "first city monument bank"),
    "fidelity": ("fidelity", "fidelity bank"),
    "union": ("union", "union bank"),
    "polaris": ("polaris", "polaris bank"),
    "stanbic": ("stanbic", "stanbic ibtc"),
    "ecobank": ("ecobank", "eco bank"),
}


def normalise(text: str) -> str:
    """Lowercase, strip accents (Yoruba diacritics) and punctuation, collapse spaces."""
    t = unicodedata.normalize("NFKD", text)
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"[’'`]", "", t.casefold())
    t = re.sub(r"[^a-z0-9]+", " ", t)
    return t.strip()


_PHRASES: list[tuple[tuple[str, ...], str]] = sorted(
    ((tuple(v.split()), key) for key, vs in _BANKS.items() for v in vs),
    key=lambda p: -len(p[0]),
)


def canonical_bank(text: str) -> str | None:
    """Canonical key if the whole text names a bank."""
    toks = tuple(normalise(text).split())
    for phrase, key in _PHRASES:
        if toks == phrase:
            return key
    return None


def extract_bank(tokens: list[str]) -> tuple[str | None, list[str]]:
    """Find a bank phrase in normalised tokens. Returns (bank key, tokens without it)."""
    for phrase, key in _PHRASES:
        n = len(phrase)
        for i in range(len(tokens) - n + 1):
            if tuple(tokens[i : i + n]) == phrase:
                return key, tokens[:i] + tokens[i + n :]
    return None, tokens
