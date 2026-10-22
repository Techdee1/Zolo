"""Any amount can have a voice: with AUDIO_PRERENDER_ON_CREATE the English and Pidgin readbacks are
rendered in the background when the agent creates the request, so the customer's readback finds the
clip. A slow or failing provider never touches the payment: the customer just gets the text."""

import asyncio
import logging
import threading
from datetime import timedelta
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


# ───────────────────────── the daily cap and the provider's quota ─────────────────────────


class _Day:
    """A clock the test moves: UTC, starting at noon."""

    def __init__(self) -> None:
        from datetime import UTC, datetime

        self.now = datetime(2026, 10, 22, 12, 0, tzinfo=UTC)

    def __call__(self):  # type: ignore[no-untyped-def]
        return self.now


async def _until_idle(prep: ReadbackAudioPreparer) -> None:
    for _ in range(200):
        if not prep._inflight:  # noqa: SLF001
            return
        await asyncio.sleep(0.01)


async def test_the_daily_cap_stops_rendering_and_the_customer_just_gets_text(
    sessionmaker, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    ai = _settings(tmp_path, monkeypatch)
    renderer, day = FakeRenderer(), _Day()
    prep = ReadbackAudioPreparer(ai, {"fake": renderer}, wait_seconds=1, daily_cap=4, clock=day)
    app = await _world(sessionmaker, prep)
    async with browser(app) as agent, browser(app) as customer:
        await login(agent, BISI_PHONE)
        await login(customer, AMAKA_PHONE)
        first = await _request(agent, customer, 11_100)  # 2 renders (en, pcm)
        second = await _request(agent, customer, 12_200)  # 2 more: the cap of 4 is reached
        await _until_idle(prep)
        third = await _request(agent, customer, 13_300)  # over the cap
        assert renderer.calls == 4
        assert prep.counts.cap_hits == 2 and prep.counts.renders == 4
        for made, expect_audio in ((first, True), (second, True), (third, False)):
            res = await customer.get(f"/requests/{made['id']}/readback?lang=en")
            assert res.status_code == 200  # never an error
            assert bool(res.json()["audio_url"]) is expect_audio
            assert res.json()["text"]
        day.now += timedelta(days=1)  # a new UTC day starts the count again
        await _request(agent, customer, 14_400)
        await _until_idle(prep)
        assert renderer.calls == 6 and prep.counts.renders == 2


async def test_a_clip_that_already_exists_costs_nothing_and_does_not_use_the_cap(
    sessionmaker, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    ai = _settings(tmp_path, monkeypatch)
    renderer = FakeRenderer()
    prep = ReadbackAudioPreparer(ai, {"fake": renderer}, wait_seconds=1, daily_cap=2, clock=_Day())
    app = await _world(sessionmaker, prep)
    async with browser(app) as agent, browser(app) as customer:
        await login(agent, BISI_PHONE)
        await login(customer, AMAKA_PHONE)
        await _request(agent, customer, 15_500)
        await _until_idle(prep)
        for _ in range(5):  # the same amount again and again: shipped or cached, never rendered
            await _request(agent, customer, 15_500)
        assert renderer.calls == 2 and prep.counts.cache_hits == 10 and prep.counts.cap_hits == 0


async def test_a_used_up_quota_stops_rendering_for_the_day_with_no_error_for_the_customer(
    sessionmaker, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    ai = _settings(tmp_path, monkeypatch)
    renderer, day = FakeRenderer(fail_with="tts_QUOTA_EXCEEDED"), _Day()
    prep = ReadbackAudioPreparer(ai, {"fake": renderer}, wait_seconds=1, daily_cap=60, clock=day)
    app = await _world(sessionmaker, prep)
    async with browser(app) as agent, browser(app) as customer:
        await login(agent, BISI_PHONE)
        await login(customer, AMAKA_PHONE)
        made = await _request(agent, customer, 16_600)
        await _until_idle(prep)
        assert prep.counts.quota_failures == 2  # both languages were refused
        calls = renderer.calls
        for amount in (17_700, 18_800):  # later requests make no attempt at all
            await _request(agent, customer, amount)
        await _until_idle(prep)
        assert renderer.calls == calls and prep.counts.paused == 4
        res = await customer.get(f"/requests/{made['id']}/readback?lang=pcm")
        assert res.status_code == 200 and res.json()["audio_url"] is None and res.json()["text"]
        day.now += timedelta(hours=13)  # the next UTC day: try again
        await _request(agent, customer, 19_900)
        await _until_idle(prep)
        assert renderer.calls > calls


async def test_a_rate_limit_only_pauses_for_ten_minutes(
    sessionmaker, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    ai = _settings(tmp_path, monkeypatch)
    renderer, day = FakeRenderer(fail_with="tts_RATE_LIMITED"), _Day()
    prep = ReadbackAudioPreparer(ai, {"fake": renderer}, wait_seconds=1, clock=day)
    app = await _world(sessionmaker, prep)
    async with browser(app) as agent, browser(app) as customer:
        await login(agent, BISI_PHONE)
        await login(customer, AMAKA_PHONE)
        await _request(agent, customer, 21_100)
        await _until_idle(prep)
        calls = renderer.calls
        await _request(agent, customer, 22_200)  # inside the pause
        await _until_idle(prep)
        assert renderer.calls == calls
        day.now += timedelta(minutes=11)
        await _request(agent, customer, 23_300)
        await _until_idle(prep)
        assert renderer.calls > calls


async def test_the_counts_are_logged_as_numbers_only(
    sessionmaker, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    records: list[logging.LogRecord] = []

    class Catch(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    log = logging.getLogger("zolo.consent.audio")
    log.setLevel(logging.INFO)
    handler = Catch()
    log.addHandler(handler)
    ai = _settings(tmp_path, monkeypatch)
    prep = ReadbackAudioPreparer(ai, {"fake": FakeRenderer()}, wait_seconds=1, clock=_Day())
    app = await _world(sessionmaker, prep)
    async with browser(app) as agent, browser(app) as customer:
        await login(agent, BISI_PHONE)
        await login(customer, AMAKA_PHONE)
        await _request(agent, customer, 24_400)
        await _until_idle(prep)
    log.removeHandler(handler)
    lines = [r.getMessage() for r in records if getattr(r, "event", "") == "audio_prepare"]
    assert lines and "renders 2" in lines[0] and "cache hits 0" in lines[0]
    assert not any("Bisi" in line or "twenty" in line for line in lines)


def test_the_cap_is_a_setting_with_a_default_of_60() -> None:
    assert make_settings().audio_daily_render_cap == 60
