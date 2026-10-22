"""Readback audio with a fallback chain, because live YarnGPT takes 4-7 seconds.

1. Cached audio bytes exist: return the URL (served from our own API) at once.
2. Otherwise return the text immediately and render in the background, which fills the cache so
   the next request is instant. A render in flight is never started twice, and a failed render is
   not retried for a minute, so a stuck provider cannot burn credits.
3. English only: tell the client to speak the text with on-device speech if audio is not ready
   within 2 seconds. Other languages get text for the screen reader instead, because a generic
   English on-device voice would mispronounce Pidgin, Yoruba, Hausa and Igbo.

The text always comes from the caller (the consent engine's stored record); this only voices it.
"""

import threading
import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass
from typing import Any, Literal

from zolo.ai.readbacks import render_readback
from zolo.ai.tts.cache import cache_key
from zolo.ai.tts.factory import RoutingTTS
from zolo.ai.types import Lang, ProviderError

DEVICE_SPEECH_AFTER_S = 2.0
RENDER_TIMEOUT_S = 30.0  # YarnGPT jobs take 4-7s; this is only a safety net
RETRY_COOLDOWN_S = 60.0

Status = Literal["ready", "rendering", "text_only"]


@dataclass(frozen=True)
class ReadbackAudio:
    text: str
    lang: str
    status: Status
    audio_url: str | None = None  # only when the audio is cached and ready
    poll_url: str | None = None  # check again here while status is "rendering"
    device_speech_after_s: float | None = None  # English only; None means "do not use it"

    def to_dict(self) -> dict[str, Any]:
        return {
            "text": self.text,
            "lang": self.lang,
            "status": self.status,
            "audio_url": self.audio_url,
            "poll_url": self.poll_url,
            "device_speech_after_s": self.device_speech_after_s,
        }


class ReadbackService:
    def __init__(
        self, tts: RoutingTTS, clock: Callable[[], float] = time.monotonic, workers: int = 2
    ) -> None:
        self.tts = tts
        self._clock = clock
        self._pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="zolo-render")
        self._lock = threading.Lock()
        self._inflight: dict[str, Future[None]] = {}
        self._cooldown: dict[str, float] = {}

    def readback_for(
        self, lang: Lang, payee: str, amount_kobo: int, wait_s: float = 0.0
    ) -> ReadbackAudio:
        """Template readback from the stored request's fields, then the fallback chain."""
        return self.get(render_readback(lang, payee, amount_kobo), lang, wait_s=wait_s)

    def get(
        self, text: str, lang: Lang, voice: str | None = None, wait_s: float = 0.0
    ) -> ReadbackAudio:
        cached = self.tts.for_lang(lang)
        voice = voice or self.tts.settings.tts_voice_for(lang)
        key = cache_key(cached.renderer.name, lang, voice, text)

        if cached.cache.get(key) is not None:
            return ReadbackAudio(text, lang, "ready", audio_url=cached.cache.url(key))

        fut = self._start_render(key, text, lang, voice) if cached.live_enabled else None
        if fut is not None and wait_s > 0:
            try:
                fut.result(timeout=wait_s)
            except (FutureTimeout, ProviderError):
                pass
            if cached.cache.get(key) is not None:
                return ReadbackAudio(text, lang, "ready", audio_url=cached.cache.url(key))

        if fut is not None:
            return ReadbackAudio(
                text, lang, "rendering", poll_url=cached.cache.url(key),
                device_speech_after_s=DEVICE_SPEECH_AFTER_S if lang == "en" else None,
            )  # fmt: skip
        return ReadbackAudio(
            text, lang, "text_only", device_speech_after_s=0.0 if lang == "en" else None
        )

    def _start_render(self, key: str, text: str, lang: Lang, voice: str) -> Future[None] | None:
        with self._lock:
            running = self._inflight.get(key)
            if running is not None:
                return running  # already rendering: do not pay twice
            if self._cooldown.get(key, 0.0) > self._clock():
                return None  # failed recently: text only, no retry yet
            fut = self._pool.submit(self._render, key, text, lang, voice)
            self._inflight[key] = fut
            return fut

    def _render(self, key: str, text: str, lang: Lang, voice: str) -> None:
        cached = self.tts.for_lang(lang)
        try:
            cached.cache.put(key, cached.renderer.render(text, lang, voice, RENDER_TIMEOUT_S))
        except ProviderError:
            with self._lock:
                self._cooldown[key] = self._clock() + RETRY_COOLDOWN_S
            raise
        finally:
            with self._lock:
                self._inflight.pop(key, None)

    def wait_idle(self, timeout: float = 5.0) -> None:
        """Block until background renders finish (tests, and graceful shutdown)."""
        with self._lock:
            pending = list(self._inflight.values())
        for f in pending:
            try:
                f.result(timeout=timeout)
            except Exception:  # noqa: BLE001 - failures are already recorded as cooldowns
                pass
