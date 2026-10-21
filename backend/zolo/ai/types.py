"""Shared types for the AI package. Money is always integer kobo."""

from dataclasses import dataclass
from typing import Literal

Lang = Literal["en", "pcm", "yo", "ha", "ig"]
LANGS: tuple[Lang, ...] = ("en", "pcm", "yo", "ha", "ig")


@dataclass(frozen=True)
class Word:
    text: str
    confidence: float | None = None


@dataclass(frozen=True)
class Transcript:
    text: str
    confidence: float | None = None  # None when the provider gives no confidence
    words: tuple[Word, ...] = ()


class ProviderError(Exception):
    """A speech provider failed or timed out. Carries a code only, never content."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code
