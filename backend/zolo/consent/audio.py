"""Readback audio (Phase 1). The readback endpoint only LOOKS UP audio: if the exact text was
rendered before, the URL is returned, otherwise there is no audio and the app lets the screen reader
speak the text. Live synthesis takes 3 to 7 seconds, so it never sits on the approval path.

So that any amount can have a voice, `ReadbackAudioPreparer` (opt in with
AUDIO_PRERENDER_ON_CREATE=true) renders the two readbacks (English and Pidgin) in the background the
moment an agent creates a request. The customer takes several seconds to claim and open it, so the
clip is usually ready by then; the readback also waits a few seconds for one that is still
rendering. If a render fails or is late the customer simply gets the text, as before."""

import asyncio
import logging
from contextlib import suppress
from typing import Protocol

from zolo.ai.config import Settings as AiSettings
from zolo.ai.tts.base import AudioRenderer
from zolo.ai.tts.cache import AudioCache, cache_key
from zolo.ai.tts.factory import RoutingTTS
from zolo.ai.types import Lang, ProviderError
from zolo.consent.readback import build_readback

log = logging.getLogger("zolo.consent.audio")


class AudioLookup(Protocol):
    def audio_url(self, text: str, lang: Lang) -> str | None: ...

    async def wait_ready(self, text: str, lang: Lang) -> None: ...


class NoAudio:
    def audio_url(self, text: str, lang: Lang) -> str | None:
        return None

    async def wait_ready(self, text: str, lang: Lang) -> None:
        return None


class ReadbackAudioPreparer:
    """Renders readback audio for a new request in the background; never raises into a request."""

    def __init__(
        self,
        ai_settings: AiSettings | None = None,
        renderers: dict[str, AudioRenderer] | None = None,
        wait_seconds: float = 4.0,
        render_timeout_s: float = 30.0,
        langs: tuple[Lang, ...] = ("en", "pcm"),
    ) -> None:
        self._ai = ai_settings or AiSettings.from_env()
        self._cache = AudioCache(self._ai.audio_cache_dir)
        self._tts = RoutingTTS(self._ai, renderers)
        self._wait, self._timeout = wait_seconds, render_timeout_s
        self._langs = langs
        self._inflight: dict[str, asyncio.Task[None]] = {}

    def _key(self, text: str, lang: Lang) -> str:
        provider = self._ai.tts_provider_for(lang)
        return cache_key(provider, lang, self._ai.tts_voice_for(lang), text)

    def schedule(self, verified_name: str, amount_kobo: int) -> None:
        """Start rendering this payee and amount in every readback language. Returns at once."""
        for lang in self._langs:
            text = build_readback(lang, verified_name, amount_kobo).text
            key = self._key(text, lang)
            if key in self._inflight or self._cache.get(key) is not None:
                continue  # already there, or already on its way: one render per sentence
            self._inflight[key] = asyncio.create_task(self._render(key, text, lang))

    async def _render(self, key: str, text: str, lang: Lang) -> None:
        voice = self._ai.tts_voice_for(lang)
        try:
            await asyncio.to_thread(
                self._tts.for_lang(lang).prerender, text, lang, voice, self._timeout
            )
        except ProviderError as exc:
            log.warning("readback audio failed", extra={"event": "audio_failed", "code": exc.code})
        except Exception as exc:  # a missing key or a network error must not touch the payment
            log.warning(
                "readback audio failed", extra={"event": "audio_failed", "code": type(exc).__name__}
            )
        finally:
            self._inflight.pop(key, None)

    async def wait_ready(self, text: str, lang: Lang) -> None:
        """If this exact readback is still being rendered, wait for it, but not for long."""
        task = self._inflight.get(self._key(text, lang))
        if task is not None:
            with suppress(TimeoutError):
                await asyncio.wait_for(asyncio.shield(task), self._wait)


class CachedAudio:
    def __init__(
        self, ai_settings: AiSettings | None = None, preparer: ReadbackAudioPreparer | None = None
    ) -> None:
        self._ai = ai_settings or AiSettings.from_env()
        self._cache = AudioCache(self._ai.audio_cache_dir)
        self._preparer = preparer

    def audio_url(self, text: str, lang: Lang) -> str | None:
        provider = self._ai.tts_provider_for(lang)
        key = cache_key(provider, lang, self._ai.tts_voice_for(lang), text)
        return self._cache.url(key) if self._cache.get(key) is not None else None

    async def wait_ready(self, text: str, lang: Lang) -> None:
        if self._preparer is not None:
            await self._preparer.wait_ready(text, lang)
