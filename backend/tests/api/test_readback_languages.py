"""Yoruba, Hausa and Igbo readbacks: the language asked for comes back only when a recording of the
exact sentence exists. Otherwise the English readback comes back with `fallback_from` set. Never a 422
for these languages, never a screen reader left to mispronounce them."""

from pathlib import Path

import pytest

from tests.api.conftest import AMAKA_PHONE, BISI_PHONE, MonotonicClock, browser, login
from tests.conftest import make_settings
from tests.integration.test_consent_engine import Clock
from zolo.ai.readbacks import render_readback
from zolo.ai.tts.base import AudioClip
from zolo.ai.tts.cache import AudioCache, cache_key
from zolo.api.main import create_app
from zolo.api.services import Overrides
from zolo.core.ratelimit import RateLimiter
from zolo.demo.seed import reset_demo

NAIRA = 100
NATIVE = ("yo", "ha", "ig")


async def _app(sessionmaker, tmp: Path, monkeypatch):  # type: ignore[no-untyped-def]
    monkeypatch.setenv("AUDIO_CACHE_DIR", str(tmp))
    settings = make_settings()
    await reset_demo(sessionmaker, settings)
    app = create_app(
        settings, overrides=Overrides(clock=Clock(), limiter=RateLimiter(MonotonicClock()))
    )
    app.state.sessionmaker = sessionmaker  # no audio override: the real CachedAudio is used
    return app


def _store(cache: AudioCache, lang: str, naira: int) -> str:
    text = render_readback(lang, "Bisi Ventures", naira * NAIRA)  # type: ignore[arg-type]
    key = cache_key("yarngpt", lang, "idera", text)
    cache.put(key, AudioClip(f"clip-{lang}".encode()))
    return key


async def _readback(agent, customer, naira: int, lang: str):  # type: ignore[no-untyped-def]
    made = (await agent.post("/agent/requests", json={"amount_kobo": naira * NAIRA})).json()
    await customer.post("/requests/claim", json={"claim_code": made["claim_code"]})
    return await customer.get(f"/requests/{made['id']}/readback?lang={lang}")


@pytest.mark.parametrize("lang", NATIVE)
async def test_the_language_asked_for_comes_back_when_its_clip_exists(
    sessionmaker, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, lang: str
) -> None:  # type: ignore[no-untyped-def]
    app = await _app(sessionmaker, tmp_path, monkeypatch)
    key = _store(AudioCache(tmp_path), lang, 15_000)
    async with browser(app) as agent, browser(app) as customer:
        await login(agent, BISI_PHONE)
        await login(customer, AMAKA_PHONE)
        res = await _readback(agent, customer, 15_000, lang)
        assert res.status_code == 200
        body = res.json()
        assert body["lang"] == lang and body["fallback_from"] is None
        assert body["audio_url"] == f"/voice/audio/{key}.mp3"
        assert body["text"] == render_readback(lang, "Bisi Ventures", 15_000 * NAIRA)  # type: ignore[arg-type]
        assert (await customer.get(body["audio_url"])).content == f"clip-{lang}".encode()


@pytest.mark.parametrize("lang", NATIVE)
async def test_without_its_clip_the_english_readback_comes_back_and_says_so(
    sessionmaker, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, lang: str
) -> None:  # type: ignore[no-untyped-def]
    app = await _app(sessionmaker, tmp_path, monkeypatch)
    async with browser(app) as agent, browser(app) as customer:
        await login(agent, BISI_PHONE)
        await login(customer, AMAKA_PHONE)
        res = await _readback(agent, customer, 7_000, lang)  # nothing was rendered
        assert res.status_code == 200  # never a 422 for these languages
        body = res.json()
        assert body["lang"] == "en" and body["fallback_from"] == lang
        assert body["text"].startswith("Bisi Ventures is asking for seven thousand naira")
        assert body["audio_url"] is None
        assert body["amount_kobo"] == 7_000 * NAIRA and body["payee_name"] == "Bisi Ventures"


async def test_the_english_clip_is_used_when_the_language_falls_back(
    sessionmaker, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    app = await _app(sessionmaker, tmp_path, monkeypatch)
    key = _store(AudioCache(tmp_path), "en", 20_000)  # English exists, Yoruba does not
    async with browser(app) as agent, browser(app) as customer:
        await login(agent, BISI_PHONE)
        await login(customer, AMAKA_PHONE)
        body = (await _readback(agent, customer, 20_000, "yo")).json()
        assert body["lang"] == "en" and body["fallback_from"] == "yo"
        assert body["audio_url"] == f"/voice/audio/{key}.mp3"


async def test_english_and_pidgin_are_unchanged_and_never_fall_back(
    sessionmaker, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    app = await _app(sessionmaker, tmp_path, monkeypatch)
    async with browser(app) as agent, browser(app) as customer:
        await login(agent, BISI_PHONE)
        await login(customer, AMAKA_PHONE)
        for lang in ("en", "pcm"):
            body = (await _readback(agent, customer, 5_000, lang)).json()
            assert body["lang"] == lang and body["fallback_from"] is None
            assert body["audio_url"] is None  # no clip stored, and the text is still there
            assert body["text"]


async def test_a_language_we_do_not_have_is_still_a_clean_422(
    sessionmaker, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    app = await _app(sessionmaker, tmp_path, monkeypatch)
    async with browser(app) as agent, browser(app) as customer:
        await login(agent, BISI_PHONE)
        await login(customer, AMAKA_PHONE)
        for lang in ("fr", "EN", ""):
            res = await _readback(agent, customer, 5_000, lang)
            assert res.status_code == 422 and res.json()["code"] == "VALIDATION_ERROR", lang


async def test_a_fallback_readback_still_moves_the_request_and_signs_the_same_intent(
    sessionmaker, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    """The language is only how it is spoken: the request and what the passkey signs do not change."""
    app = await _app(sessionmaker, tmp_path, monkeypatch)
    async with browser(app) as agent, browser(app) as customer:
        await login(agent, BISI_PHONE)
        await login(customer, AMAKA_PHONE)
        made = (await agent.post("/agent/requests", json={"amount_kobo": 5_000 * NAIRA})).json()
        await customer.post("/requests/claim", json={"claim_code": made["claim_code"]})
        await customer.get(f"/requests/{made['id']}/readback?lang=ig")
        state = (await customer.get(f"/requests/{made['id']}")).json()["state"]
        assert state == "READ_BACK"
