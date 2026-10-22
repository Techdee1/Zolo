import hashlib

from zolo.ai.tts.base import AudioClip
from zolo.ai.types import Lang, ProviderError


class FakeTTS:
    def __init__(self, fail_with: str | None = None) -> None:
        self.fail_with = fail_with
        self.calls = 0

    def synthesize(self, text: str, lang: Lang, voice: str) -> str | None:
        self.calls += 1
        if self.fail_with:
            raise ProviderError(self.fail_with)
        digest = hashlib.sha256(f"{lang}|{voice}|{text}".encode()).hexdigest()[:16]
        return f"fake://audio/{digest}.mp3"


class FakeRenderer:
    """Offline renderer: deterministic fake mp3 bytes."""

    name = "fake"

    def __init__(self, fail_with: str | None = None) -> None:
        self.fail_with = fail_with
        self.calls = 0

    def render(self, text: str, lang: Lang, voice: str, timeout_s: float) -> AudioClip:
        self.calls += 1
        if self.fail_with:
            raise ProviderError(self.fail_with)
        return AudioClip(f"FAKE-MP3|{lang}|{voice}|{text}".encode())
