"""The objects the routes share, built once per app on first use (after the database exists)."""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from fastapi import FastAPI

from zolo.ai.config import Settings as AiSettings
from zolo.ai.tts.cache import AudioCache
from zolo.ai.types import LANGS
from zolo.bank.adapter import BankAdapter
from zolo.bank.mock import Latency, MockBankAdapter
from zolo.consent.audio import AudioLookup, CachedAudio, ReadbackAudioPreparer
from zolo.consent.service import ConsentService
from zolo.core.config import Settings
from zolo.core.ratelimit import RateLimiter
from zolo.core.security import SessionCodec
from zolo.demo.store import DemoStore
from zolo.passkeys.service import PasskeyService


@dataclass
class Overrides:
    """Test hooks: swap the bank, the clock, the audio lookup or the limiter."""

    bank: BankAdapter | None = None
    clock: Any = None
    audio: AudioLookup | None = None
    limiter: RateLimiter | None = None
    audio_prep: ReadbackAudioPreparer | None = None


@dataclass
class Services:
    settings: Settings
    bank: BankAdapter
    consent: ConsentService
    passkeys: PasskeyService
    limiter: RateLimiter
    codec: SessionCodec
    audio_cache: AudioCache
    audio_prep: ReadbackAudioPreparer | None
    sessionmaker: Any
    demo: DemoStore | None  # only when DEMO_MODE=true


def build_services(app: FastAPI) -> Services:
    settings: Settings = app.state.settings
    overrides: Overrides = app.state.overrides
    clock = overrides.clock or (lambda: datetime.now(UTC))
    bank = overrides.bank or MockBankAdapter(
        app.state.sessionmaker,
        home_bank_code=settings.mock_bank_code,
        latency=Latency(settings.mock_bank_latency_min_ms, settings.mock_bank_latency_max_ms),
    )
    ai = AiSettings.from_env()
    passkeys = PasskeyService(settings, clock)
    audio_prep = overrides.audio_prep or (
        ReadbackAudioPreparer(
            ai,
            wait_seconds=settings.audio_wait_seconds,
            langs=tuple(
                lang
                for lang in LANGS
                if lang in settings.audio_prerender_langs.replace(" ", "").split(",")
            ),
        )
        if settings.audio_prerender_on_create
        else None
    )
    consent = ConsentService(
        settings,
        bank,
        audio=overrides.audio or CachedAudio(ai, audio_prep),
        clock=clock,
        passkeys=passkeys,
    )
    return Services(
        settings=settings,
        bank=bank,
        consent=consent,
        passkeys=passkeys,
        limiter=overrides.limiter or RateLimiter(),
        codec=SessionCodec(settings.session_secret, settings.session_ttl_seconds),
        audio_cache=AudioCache(ai.audio_cache_dir),
        audio_prep=audio_prep,
        sessionmaker=app.state.sessionmaker,
        demo=DemoStore() if settings.demo_mode else None,
    )
