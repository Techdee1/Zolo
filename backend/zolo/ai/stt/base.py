from collections.abc import Sequence
from typing import Protocol

from zolo.ai.types import Lang, Transcript


class SpeechToText(Protocol):
    def transcribe(
        self, audio: bytes, mime: str, lang: Lang, special_words: Sequence[str] = ()
    ) -> Transcript: ...
