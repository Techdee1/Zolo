"""Any amount can have a voice: with AUDIO_PRERENDER_ON_CREATE the English and Pidgin readbacks are
rendered in the background when the agent creates the request, so the customer's readback finds the
clip. A slow or failing provider never touches the payment: the customer just gets the text."""

import asyncio
import logging
import threading
from pathlib import Path

import pytest

from tests.api.conftest import AMAKA_PHONE, BISI_PHONE, MonotonicClock, browser, login
from tests.conftest import make_settings
from tests.integration.test_consent_engine import Clock
from zolo.ai.config import Settings as AiSettings
from zolo.ai.tts.base import AudioClip
from zolo.ai.tts.fake import FakeRenderer
from zolo.ai.types import Lang, ProviderError
from zolo.api.main import create_app
from zolo.api.services import Overrides
from zolo.consent.audio import ReadbackAudioPreparer
from zolo.core.ratelimit import RateLimiter
from zolo.demo.seed import reset_demo

NAIRA = 100


class SlowRenderer(FakeRenderer):
    """Holds each render until the test lets it go, like a provider that takes its time."""

    def __init__(self) -> None:
        super().__init__()
        self.release = threading.Event()

    def render(self, text: str, lang: Lang, voice: str, timeout_s: float) -> AudioClip:
        self.release.wait(10)
        return super().render(text, lang, voice, timeout_s)


def _settings(tmp: Path, monkeypatch: pytest.MonkeyPatch) -> AiSettings:
    monkeypatch.setenv("AUDIO_CACHE_DIR", str(tmp))
    for lang in ("EN", "PCM", "YO", "HA", "IG"):
        monkeypatch.setenv(f"TTS_PROVIDER_{lang}", "fake")
    return AiSettings.from_env()


async def _world(sessionmaker, prep):  # type: ignore[no-untyped-def]
    settings = make_settings()
    await reset_demo(sessionmaker, settings)
    app = create_app(
        settings,
        overrides=Overrides(clock=Clock(), limiter=RateLimiter(MonotonicClock()), audio_prep=prep),
    )
    app.state.sessionmaker = sessionmaker
    return app


async def _request(agent, customer, naira: int):  # type: ignore[no-untyped-def]
    made = (await agent.post("/agent/requests", json={"amount_kobo": naira * NAIRA})).json()
    await customer.post("/requests/claim", json={"claim_code": made["claim_code"]})
    return made


async def test_any_amount_gets_audio_in_both_languages(
    sessionmaker, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    ai = _settings(tmp_path, monkeypatch)
    renderer = FakeRenderer()
    prep = ReadbackAudioPreparer(ai, {"fake": renderer}, wait_seconds=3)
    app = await _world(sessionmaker, prep)
    # CachedAudio is built from the same environment, so it finds what the preparer rendered.
    async with browser(app) as agent, browser(app) as customer:
        await login(agent, BISI_PHONE)
        await login(customer, AMAKA_PHONE)
        made = await _request(agent, customer, 7_300)  # an amount nobody pre-rendered
        for lang in ("en", "pcm"):
            body = (await customer.get(f"/requests/{made['id']}/readback?lang={lang}")).json()
            assert body["audio_url"], lang
            clip = await customer.get(body["audio_url"])
            assert clip.status_code == 200 and body["text"].encode() in clip.content
    assert renderer.calls == 2  # one render per language, no more


async def test_the_same_sentence_is_rendered_once(
    sessionmaker, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    ai = _settings(tmp_path, monkeypatch)
    renderer = FakeRenderer()
    prep = ReadbackAudioPreparer(ai, {"fake": renderer}, wait_seconds=3)
    app = await _world(sessionmaker, prep)
    async with browser(app) as agent, browser(app) as customer:
        await login(agent, BISI_PHONE)
        await login(customer, AMAKA_PHONE)
        for _ in range(3):
            made = await _request(agent, customer, 9_000)
            await customer.get(f"/requests/{made['id']}/readback?lang=en")
    assert renderer.calls == 2  # ₦9,000 in en and pcm, once, however many requests asked for it


async def test_a_late_clip_never_blocks_the_readback_and_is_there_next_time(
    sessionmaker, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    ai = _settings(tmp_path, monkeypatch)
    renderer = SlowRenderer()
    prep = ReadbackAudioPreparer(ai, {"fake": renderer}, wait_seconds=0.2)
    app = await _world(sessionmaker, prep)
    async with browser(app) as agent, browser(app) as customer:
        await login(agent, BISI_PHONE)
        await login(customer, AMAKA_PHONE)
        made = await _request(agent, customer, 4_400)
        first = (await customer.get(f"/requests/{made['id']}/readback?lang=en")).json()
        assert first["audio_url"] is None and first["text"]  # waited 0.2 s, then gave the text
        renderer.release.set()
        await asyncio.sleep(0.3)
        again = (await customer.get(f"/requests/{made['id']}/readback?lang=en")).json()
        assert again["audio_url"]  # the clip arrived; "Hear again" and a re-read now have it


async def test_a_failing_provider_changes_nothing_for_the_customer(
    sessionmaker, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    records: list[logging.LogRecord] = []

    class Catch(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    log = logging.getLogger("zolo.consent.audio")
    handler = Catch()
    log.addHandler(handler)
    ai = _settings(tmp_path, monkeypatch)
    renderer = FakeRenderer(fail_with="timeout")
    prep = ReadbackAudioPreparer(ai, {"fake": renderer}, wait_seconds=1)
    app = await _world(sessionmaker, prep)
    async with browser(app) as agent, browser(app) as customer:
        await login(agent, BISI_PHONE)
        await login(customer, AMAKA_PHONE)
        made = await _request(agent, customer, 6_100)
        res = await customer.get(f"/requests/{made['id']}/readback?lang=pcm")
        assert res.status_code == 200
        body = res.json()
        assert body["audio_url"] is None and body["text"].startswith("Bisi Ventures dey ask")
    log.removeHandler(handler)
    logged = " ".join(r.getMessage() + str(getattr(r, "code", "")) for r in records)
    assert "timeout" in logged and "Bisi" not in logged  # the reason code only, never the words


async def test_a_missing_api_key_is_a_quiet_text_only_readback(
    sessionmaker, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    class NoKey(FakeRenderer):
        def render(self, text: str, lang: Lang, voice: str, timeout_s: float) -> AudioClip:
            raise RuntimeError("YARNGPT_API_KEY is not set")

    ai = _settings(tmp_path, monkeypatch)
    prep = ReadbackAudioPreparer(ai, {"fake": NoKey()}, wait_seconds=1)
    app = await _world(sessionmaker, prep)
    async with browser(app) as agent, browser(app) as customer:
        await login(agent, BISI_PHONE)
        await login(customer, AMAKA_PHONE)
        made = await _request(agent, customer, 3_300)
        body = (await customer.get(f"/requests/{made['id']}/readback?lang=en")).json()
        assert body["audio_url"] is None and body["text"]


async def test_off_by_default_nothing_is_rendered(
    sessionmaker, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    _settings(tmp_path, monkeypatch)
    settings = make_settings()
    assert settings.audio_prerender_on_create is False
    app = await _world(sessionmaker, None)
    async with browser(app) as agent, browser(app) as customer:
        await login(agent, BISI_PHONE)
        await login(customer, AMAKA_PHONE)
        made = await _request(agent, customer, 2_200)
        body = (await customer.get(f"/requests/{made['id']}/readback?lang=en")).json()
        assert body["audio_url"] is None
    assert not list(tmp_path.glob("*.mp3"))


def test_provider_errors_carry_a_code_only() -> None:
    assert ProviderError("timeout").code == "timeout"
