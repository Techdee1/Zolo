"""Spitch speech to text.

Verified against the docs and the installed SDK (not the PRD's assumptions):
- accepts mp3, wav, m4a, ogg (not webm), max 25 MB, so audio is converted first;
- language codes en, yo, ha, ig; there is no Pidgin code, so pcm uses the English model;
- the response has no confidence, so Transcript.confidence is always None.
Data retention terms are unconfirmed. The SDK sends X-Data-Retention: True by default; we send
False, but we do not know that Spitch honours it.
"""

from collections.abc import Sequence
from pathlib import Path
from typing import Any

from zolo.ai.config import Settings, api_key
from zolo.ai.stt.audio import to_wav_16k_mono
from zolo.ai.types import Lang, ProviderError, Transcript
from zolo.ai.usage import count_call

SPITCH_LANG: dict[Lang, str] = {"en": "en", "pcm": "en", "yo": "yo", "ha": "ha", "ig": "ig"}
MONEY_WORDS = ("k", "naira", "thousand", "hundred", "million")
# The docs do not say how special_words is formatted; a comma separated string is our assumption.


class SpitchSTT:
    def __init__(self, settings: Settings | None = None, client: Any = None) -> None:
        self.settings = settings or Settings.from_env()
        self._client = client
        self._count_file: Path = self.settings.stt_call_count_file

    def _get_client(self) -> Any:
        if self._client is None:
            from spitch import Spitch

            self._client = Spitch(
                api_key=api_key("SPITCH_API_KEY"),
                data_retention=False,
                timeout=self.settings.request_timeout_s,
                max_retries=0,  # the service owns retries and the 5-second budget
            )
        return self._client

    def transcribe(
        self, audio: bytes, mime: str, lang: Lang, special_words: Sequence[str] = ()
    ) -> Transcript:
        if not self.settings.stt_live_enabled:
            raise ProviderError("stt_disabled")
        wav = to_wav_16k_mono(audio, self.settings.request_timeout_s)
        # Recipient and bank names first (they matter most), money words always, capped in size.
        words = ", ".join(list(dict.fromkeys([*special_words, *MONEY_WORDS]))[:60])
        count_call(self._count_file, "spitch")
        try:
            resp = self._get_client().speech.transcribe(
                content=wav, language=SPITCH_LANG[lang], special_words=words
            )
        except Exception as exc:
            raise ProviderError(_code(exc)) from None  # never carry provider text
        return Transcript(text=(resp.text or "").strip(), confidence=None)


def _code(exc: Exception) -> str:
    name = type(exc).__name__.lower()
    if "timeout" in name:
        return "stt_timeout"
    if "ratelimit" in name:
        return "stt_rate_limited"
    if "authentication" in name or "permission" in name:
        return "stt_auth"
    return "stt_error"
