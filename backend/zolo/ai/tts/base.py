from dataclasses import dataclass
from typing import Protocol

from zolo.ai.types import Lang


@dataclass(frozen=True)
class AudioClip:
    data: bytes
    mime: str = "audio/mpeg"


class AudioRenderer(Protocol):
    """A provider that turns text into audio bytes."""

    name: str

    def render(self, text: str, lang: Lang, voice: str, timeout_s: float) -> AudioClip: ...


class TextToSpeech(Protocol):
    def synthesize(self, text: str, lang: Lang, voice: str) -> str | None:
        """Return a URL the app can play, or None when only text is available.

        None means the app lets the screen reader speak the text.
        """
        ...
