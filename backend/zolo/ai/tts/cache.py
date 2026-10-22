"""Audio cache keyed by hash of (provider, lang, voice, text). Stores bytes, never URLs.

Provider links expire after about an hour, so we keep the audio and serve it ourselves.
The text is hashed, not stored, so the cache directory holds no readable payment details.
"""

import hashlib
from pathlib import Path

from zolo.ai.tts.base import AudioClip, AudioRenderer
from zolo.ai.tts.compress import compress_mp3
from zolo.ai.types import Lang, ProviderError

AUDIO_URL_PREFIX = "/voice/audio/"


def cache_key(provider: str, lang: str, voice: str, text: str) -> str:
    return hashlib.sha256("\x1f".join((provider, lang, voice, text)).encode()).hexdigest()


class AudioCache:
    def __init__(self, directory: Path) -> None:
        self.dir = directory

    def _path(self, key: str) -> Path:
        if not key.isalnum():
            raise ValueError("bad cache key")
        return self.dir / f"{key}.mp3"

    def get(self, key: str) -> AudioClip | None:
        try:
            return AudioClip(self._path(key).read_bytes())
        except OSError:
            return None

    def put(self, key: str, clip: AudioClip) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        tmp = self._path(key).with_suffix(".tmp")
        tmp.write_bytes(clip.data)
        tmp.replace(self._path(key))  # atomic: a reader never sees half a file

    def url(self, key: str) -> str:
        return f"{AUDIO_URL_PREFIX}{key}.mp3"


class CachedTTS:
    """TextToSpeech with the PRD's ladder: cache, then live (within budget), then text only."""

    def __init__(
        self,
        renderer: AudioRenderer,
        cache: AudioCache,
        live_enabled: bool,
        live_budget_s: float = 2.0,
    ) -> None:
        self.renderer, self.cache = renderer, cache
        self.live_enabled, self.live_budget_s = live_enabled, live_budget_s
        self.last_source = ""  # "cache" | "live" | "text_only", for timing logs and tests

    def synthesize(self, text: str, lang: Lang, voice: str) -> str | None:
        key = cache_key(self.renderer.name, lang, voice, text)
        if self.cache.get(key) is not None:
            self.last_source = "cache"
            return self.cache.url(key)
        if self.live_enabled:
            try:
                clip = self.renderer.render(text, lang, voice, self.live_budget_s)
                self.cache.put(key, AudioClip(compress_mp3(clip.data), clip.mime))
                self.last_source = "live"
                return self.cache.url(key)
            except ProviderError:
                pass
        self.last_source = "text_only"
        return None

    def prerender(self, text: str, lang: Lang, voice: str, timeout_s: float = 30.0) -> bool:
        """Render and store one line (for the demo script). Returns True if it was new."""
        key = cache_key(self.renderer.name, lang, voice, text)
        if self.cache.get(key) is not None:
            return False
        clip = self.renderer.render(text, lang, voice, timeout_s)
        self.cache.put(key, AudioClip(compress_mp3(clip.data), clip.mime))
        return True
