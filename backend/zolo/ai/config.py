"""Settings from environment variables. Keys are never read from files in the repo."""

import os
from dataclasses import dataclass, field
from pathlib import Path

from zolo.ai.types import LANGS, Lang


def load_dotenv(path: Path | None = None) -> None:
    """Load backend/.env (gitignored) without overriding real environment variables."""
    path = path or Path(__file__).resolve().parents[2] / ".env"
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.split(" #")[0].strip())


# YarnGPT's own default voice (GET /api/v1/voices). Change per language with TTS_VOICE_<LANG>
# after a listening test; nobody here has judged which voice is most natural yet.
DEFAULT_VOICE = "idera"


def _flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    return default if raw is None else raw.strip().lower() in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Settings:
    stt_live_enabled: bool = False
    stt_provider: str = "spitch"
    tts_live_enabled: bool = False
    ai_agent_enabled: bool = False  # Phase 2; nothing reads it yet
    allow_text_input: bool = False
    audio_cache_dir: Path = Path("var/audio")
    stt_call_count_file: Path = Path("var/stt_calls.json")
    request_timeout_s: float = 5.0
    tts_live_budget_s: float = 2.0
    reply_audio_wait_s: float = 0.0  # how long a voice reply waits for audio before text-only
    tts_providers: dict[str, str] = field(default_factory=dict)
    tts_voices: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            stt_live_enabled=_flag("STT_LIVE_ENABLED", False),
            stt_provider=os.environ.get("STT_PROVIDER", "spitch"),
            tts_live_enabled=_flag("TTS_LIVE_ENABLED", False),
            ai_agent_enabled=_flag("AI_AGENT_ENABLED", False),
            allow_text_input=_flag("ALLOW_TEXT_INPUT", False),
            audio_cache_dir=Path(os.environ.get("AUDIO_CACHE_DIR", "var/audio")),
            stt_call_count_file=Path(os.environ.get("STT_CALL_COUNT_FILE", "var/stt_calls.json")),
            tts_providers={
                lang: os.environ.get(f"TTS_PROVIDER_{lang.upper()}", "yarngpt") for lang in LANGS
            },
            tts_voices={
                lang: os.environ.get(f"TTS_VOICE_{lang.upper()}", DEFAULT_VOICE) for lang in LANGS
            },
        )

    def tts_voice_for(self, lang: Lang) -> str:
        return self.tts_voices.get(lang, DEFAULT_VOICE)

    def tts_provider_for(self, lang: Lang) -> str:
        return self.tts_providers.get(lang, "yarngpt")


def api_key(name: str) -> str:
    key = os.environ.get(name, "")
    if not key:
        raise RuntimeError(f"{name} is not set")  # the name only, never the value
    return key
