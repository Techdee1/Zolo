from collections.abc import Sequence

from zolo.ai.types import Lang, ProviderError, Transcript


class FakeSTT:
    """Offline STT. Returns the audio bytes decoded as text, so tests pass text as 'audio'."""

    def __init__(self, confidence: float | None = 0.95, fail_with: str | None = None) -> None:
        self.confidence = confidence
        self.fail_with = fail_with
        self.calls = 0
        self.last_special_words: tuple[str, ...] = ()

    def transcribe(
        self, audio: bytes, mime: str, lang: Lang, special_words: Sequence[str] = ()
    ) -> Transcript:
        self.calls += 1
        self.last_special_words = tuple(special_words)
        if self.fail_with:
            raise ProviderError(self.fail_with)
        return Transcript(text=audio.decode("utf-8"), confidence=self.confidence)
