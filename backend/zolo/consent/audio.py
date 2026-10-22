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
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
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


RATE_LIMIT_PAUSE = timedelta(minutes=10)  # the provider said "too fast": give it a rest


@dataclass
class AudioCounts:
    """What the preparer has done today, in numbers only (never the words)."""

    renders: int = 0  # renders started
    cache_hits: int = 0  # sentences that already had a clip (shipped or rendered before)
    cap_hits: int = 0  # sentences not rendered because the daily cap was reached
    quota_failures: int = 0  # renders the provider refused (quota or rate limit)
    paused: int = 0  # sentences not rendered because the provider had said to stop


class ReadbackAudioPreparer:
    """Renders readback audio for a new request in the background; never raises into a request.

    Credits are protected three ways: a clip that already exists (shipped or rendered before) is
    never rendered again; at most `daily_cap` renders start per UTC day (counted in memory, so the
    count also restarts with the process, which is fine for one dyno); and when the provider says
    its quota is used up the preparer stops for the rest of the day (ten minutes if it only said
    "too fast").
    In every one of those cases the customer just gets the text, with no error.
    """

    def __init__(
        self,
        ai_settings: AiSettings | None = None,
        renderers: dict[str, AudioRenderer] | None = None,
        wait_seconds: float = 4.0,
        render_timeout_s: float = 30.0,
        langs: tuple[Lang, ...] = ("en", "pcm"),
        daily_cap: int = 60,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._ai = ai_settings or AiSettings.from_env()
        self._cache = AudioCache(self._ai.audio_cache_dir)
        self._tts = RoutingTTS(self._ai, renderers)
        self._wait, self._timeout = wait_seconds, render_timeout_s
        self._langs = langs
        self._cap, self._clock = daily_cap, clock
        self._inflight: dict[str, asyncio.Task[None]] = {}
        self._day = clock().date()
        self._paused_until: datetime | None = None
        self.counts = AudioCounts()

    def _roll_the_day(self) -> None:
        """A new UTC day starts the count (and any pause for quota) from zero."""
        now = self._clock()
        if now.date() != self._day:
            self._day, self.counts, self._paused_until = now.date(), AudioCounts(), None

    def _may_render(self) -> bool:
        self._roll_the_day()
        if self._paused_until is not None and self._clock() < self._paused_until:
            self.counts.paused += 1
            return False
        if self.counts.renders >= self._cap:
            self.counts.cap_hits += 1
            return False
        return True

    def _key(self, text: str, lang: Lang) -> str:
        provider = self._ai.tts_provider_for(lang)
        return cache_key(provider, lang, self._ai.tts_voice_for(lang), text)

    def schedule(self, verified_name: str, amount_kobo: int) -> None:
        """Start rendering this payee and amount in every readback language. Returns at once."""
        before = AudioCounts(**vars(self.counts))
        self._roll_the_day()
        for lang in self._langs:
            text = build_readback(lang, verified_name, amount_kobo).text
            key = self._key(text, lang)
            if key in self._inflight:
                continue  # already on its way: one render per sentence
            if self._cache.get(key) is not None:
                self.counts.cache_hits += 1
                continue
            if not self._may_render():
                continue  # over the cap, or the provider asked us to stop: text only
            self.counts.renders += 1
            self._inflight[key] = asyncio.create_task(self._render(key, text, lang))
        now = self.counts
        log.info(
            "readback audio: renders %d, cache hits %d, cap hits %d, paused %d, quota failures %d"
            " (today: %d renders of %d)",
            now.renders - before.renders, now.cache_hits - before.cache_hits,
            now.cap_hits - before.cap_hits, now.paused - before.paused,
            now.quota_failures - before.quota_failures, now.renders, self._cap,
            extra={"event": "audio_prepare", "renders_today": now.renders},
        )  # fmt: skip

    async def _render(self, key: str, text: str, lang: Lang) -> None:
        voice = self._ai.tts_voice_for(lang)
        try:
            await asyncio.to_thread(
                self._tts.for_lang(lang).prerender, text, lang, voice, self._timeout
            )
        except ProviderError as exc:
            code = exc.code.upper()
            if "QUOTA" in code or "RATE" in code:
                self.counts.quota_failures += 1
                now = self._clock()
                self._paused_until = (
                    now + RATE_LIMIT_PAUSE
                    if "RATE" in code and "QUOTA" not in code
                    else datetime.combine(now.date() + timedelta(days=1), datetime.min.time(), UTC)
                )
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
