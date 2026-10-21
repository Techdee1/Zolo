"""The real audio path (no stub): a readback whose exact words were pre-rendered gets an audio
URL, that URL serves the clip, and a readback nobody rendered gets none."""

from pathlib import Path

import pytest
from httpx import AsyncClient

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


async def test_prerendered_readbacks_get_audio_and_others_do_not(
    sessionmaker, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("AUDIO_CACHE_DIR", str(tmp_path))
    settings = make_settings()
    await reset_demo(sessionmaker, settings)
    app = create_app(
        settings, overrides=Overrides(clock=Clock(), limiter=RateLimiter(MonotonicClock()))
    )
    app.state.sessionmaker = (
        sessionmaker  # note: no audio override, so the real CachedAudio is used
    )

    # "render" the ₦15,000 Pidgin readback in the cache, exactly as the pre-render tool would
    words = render_readback("pcm", "Bisi Ventures", 15_000 * NAIRA)
    key = cache_key("yarngpt", "pcm", "idera", words)
    AudioCache(tmp_path).put(key, AudioClip(b"ID3-demo-clip"))

    async with browser(app) as agent, browser(app) as customer:
        await login(agent, BISI_PHONE)
        await login(customer, AMAKA_PHONE)

        async def readback_for(naira: int, lang: str = "pcm") -> dict:  # type: ignore[type-arg]
            made = (await agent.post("/agent/requests", json={"amount_kobo": naira * NAIRA})).json()
            await customer.post("/requests/claim", json={"claim_code": made["claim_code"]})
            return (await customer.get(f"/requests/{made['id']}/readback?lang={lang}")).json()  # type: ignore[no-any-return]

        rendered = await readback_for(15_000)
        assert rendered["audio_url"] == f"/voice/audio/{key}.mp3"
        clip = await customer.get(rendered["audio_url"])
        assert clip.status_code == 200 and clip.content == b"ID3-demo-clip"

        assert (await readback_for(15_000, "en"))["audio_url"] is None  # English was not rendered
        assert (await readback_for(7_000))["audio_url"] is None  # nor was this amount
        assert (await readback_for(7_000))["text"].startswith(
            "Bisi Ventures dey ask"
        )  # but the text is there


async def test_the_audio_endpoint_works_without_logging_in(anonymous: AsyncClient) -> None:
    # the key is unguessable (a SHA-256 of the exact words); a missing one is a clean 404
    assert (await anonymous.get(f"/voice/audio/{'a' * 64}.mp3")).status_code == 404
