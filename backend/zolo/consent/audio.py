"""Pre-rendered readback audio (Phase 1). Cache only: if the exact text was rendered before the
URL is returned, otherwise there is no audio and the app lets the screen reader speak the text.
Live synthesis takes 3 to 7 seconds, so it never sits on the approval path."""

from typing import Protocol

from zolo.ai.config import Settings as AiSettings
from zolo.ai.tts.cache import AudioCache, cache_key
from zolo.ai.types import Lang


class AudioLookup(Protocol):
    def audio_url(self, text: str, lang: Lang) -> str | None: ...


class NoAudio:
    def audio_url(self, text: str, lang: Lang) -> str | None:
        return None


class CachedAudio:
    def __init__(self, ai_settings: AiSettings | None = None) -> None:
        self._ai = ai_settings or AiSettings.from_env()
        self._cache = AudioCache(self._ai.audio_cache_dir)

    def audio_url(self, text: str, lang: Lang) -> str | None:
        provider = self._ai.tts_provider_for(lang)
        key = cache_key(provider, lang, self._ai.tts_voice_for(lang), text)
        return self._cache.url(key) if self._cache.get(key) is not None else None
