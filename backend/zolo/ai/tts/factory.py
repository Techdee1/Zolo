"""Build the TTS used by the service: provider chosen per language from settings."""

from zolo.ai.config import Settings
from zolo.ai.tts.base import AudioRenderer
from zolo.ai.tts.cache import AudioCache, CachedTTS
from zolo.ai.tts.fake import FakeRenderer
from zolo.ai.tts.yarngpt import YarnGPTRenderer
from zolo.ai.types import Lang


def make_renderer(provider: str) -> AudioRenderer:
    if provider == "yarngpt":
        return YarnGPTRenderer()
    if provider == "fake":
        return FakeRenderer()
    raise ValueError(f"unknown TTS provider: {provider}")


class RoutingTTS:
    """One CachedTTS per provider; each language uses the provider set for it."""

    def __init__(
        self, settings: Settings, renderers: dict[str, AudioRenderer] | None = None
    ) -> None:
        self.settings = settings
        cache = AudioCache(settings.audio_cache_dir)
        self._by_provider: dict[str, CachedTTS] = {}
        for provider in set(settings.tts_providers.values()) | {"yarngpt"}:
            renderer = (renderers or {}).get(provider) or make_renderer(provider)
            self._by_provider[provider] = CachedTTS(
                renderer, cache, settings.tts_live_enabled, settings.tts_live_budget_s
            )

    def for_lang(self, lang: Lang) -> CachedTTS:
        return self._by_provider[self.settings.tts_provider_for(lang)]

    def synthesize(self, text: str, lang: Lang, voice: str | None = None) -> str | None:
        return self.for_lang(lang).synthesize(
            text, lang, voice or self.settings.tts_voice_for(lang)
        )
