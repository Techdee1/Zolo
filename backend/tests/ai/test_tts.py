import json

import httpx
import pytest

from zolo.ai.config import Settings
from zolo.ai.demo_script import demo_lines
from zolo.ai.readbacks import load_template, render_readback
from zolo.ai.tts.cache import AudioCache, CachedTTS, cache_key
from zolo.ai.tts.factory import RoutingTTS
from zolo.ai.tts.fake import FakeRenderer
from zolo.ai.tts.yarngpt import YarnGPTRenderer
from zolo.ai.types import LANGS, ProviderError


def test_cache_key_depends_on_every_part():
    base = cache_key("yarngpt", "en", "idera", "hello")
    assert base == cache_key("yarngpt", "en", "idera", "hello")
    for other in [("fake", "en", "idera", "hello"), ("yarngpt", "pcm", "idera", "hello"),
                  ("yarngpt", "en", "jude", "hello"), ("yarngpt", "en", "idera", "hello!")]:  # fmt: skip
        assert cache_key(*other) != base


def test_cache_stores_bytes_not_text(tmp_path):
    r = FakeRenderer()
    tts = CachedTTS(r, AudioCache(tmp_path), live_enabled=True)
    url = tts.synthesize("Bisi Ventures dey ask", "pcm", "idera")
    assert url and url.startswith("/voice/audio/") and tts.last_source == "live"
    assert [p.suffix for p in tmp_path.iterdir()] == [".mp3"]
    assert "Bisi" not in next(tmp_path.iterdir()).name
    assert tts.synthesize("Bisi Ventures dey ask", "pcm", "idera") == url
    assert tts.last_source == "cache" and r.calls == 1


def test_cache_serves_when_live_is_off_and_text_only_when_empty(tmp_path):
    cache = AudioCache(tmp_path)
    CachedTTS(FakeRenderer(), cache, live_enabled=True).synthesize("hi", "en", "v")
    off = CachedTTS(FakeRenderer(), cache, live_enabled=False)
    assert off.synthesize("hi", "en", "v") is not None and off.last_source == "cache"
    assert off.synthesize("never rendered", "en", "v") is None and off.last_source == "text_only"
    assert off.renderer.calls == 0


def test_live_failure_falls_back_to_text_only(tmp_path):
    tts = CachedTTS(FakeRenderer(fail_with="tts_timeout"), AudioCache(tmp_path), live_enabled=True)
    assert tts.synthesize("hello", "en", "v") is None and tts.last_source == "text_only"


def test_cache_rejects_path_tricks(tmp_path):
    with pytest.raises(ValueError):
        AudioCache(tmp_path).get("../../etc/passwd")


def test_routing_picks_provider_per_language(tmp_path):
    s = Settings(
        audio_cache_dir=tmp_path, tts_live_enabled=True,
        tts_providers={"en": "yarngpt", "pcm": "fake", "yo": "yarngpt", "ha": "yarngpt", "ig": "yarngpt"},
        tts_voices={lang: "v" for lang in LANGS},
    )  # fmt: skip
    fake, other = FakeRenderer(), FakeRenderer()
    other.name = "yarngpt"
    r = RoutingTTS(s, {"fake": fake, "yarngpt": other})
    r.synthesize("a", "pcm")
    r.synthesize("b", "en")
    assert (fake.calls, other.calls) == (1, 1)  # switching a language is config only


# --- YarnGPT against a mocked HTTP server: no credits used ---


def _yarn(handler):
    ticks = iter(range(1000))
    client = httpx.Client(base_url="https://api.yarngpt.ai", transport=httpx.MockTransport(handler))
    return YarnGPTRenderer(client, key="KEY", sleep=lambda s: None, clock=lambda: next(ticks) * 0.1)


def test_yarngpt_job_flow_and_request_shape(monkeypatch):
    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        if req.method == "POST":
            seen["post"] = req
            return httpx.Response(202, json={"job_id": "j1", "status": "queued"})
        polls = seen.setdefault("polls", [])
        polls.append(1)
        if len(polls) < 2:
            return httpx.Response(200, json={"status": "processing", "audio_url": None})
        return httpx.Response(
            200, json={"status": "completed", "audio_url": "https://files.example/a.mp3"}
        )

    monkeypatch.setattr(httpx, "get", lambda url, **kw: httpx.Response(200, content=b"MP3DATA"))
    clip = _yarn(handler).render("Ten naira", "pcm", "idera", 10)
    assert clip.data == b"MP3DATA"
    req = seen["post"]
    body = json.loads(req.content)
    assert body == {
        "text": "Ten naira",
        "voice": "idera",
        "output_format": "mp3",
        "target_language": "en",
    }
    assert req.headers["Authorization"] == "Bearer KEY" and req.headers["Idempotency-Key"]


def test_yarngpt_download_does_not_send_our_key(monkeypatch):
    sent = {}

    def fake_get(url, **kw):
        sent.update(kw)
        return httpx.Response(200, content=b"x")

    def handler(req):
        if req.method == "POST":
            return httpx.Response(202, json={"job_id": "j"})
        return httpx.Response(200, json={"status": "completed", "audio_url": "https://cdn/a.mp3"})

    monkeypatch.setattr(httpx, "get", fake_get)
    _yarn(handler).render("t", "en", "idera", 10)
    assert "headers" not in sent


@pytest.mark.parametrize(
    "handler,code",
    [
        (lambda r: httpx.Response(401, json={"error": {"code": "invalid_api_key", "message": "secret words"}}),
         "tts_invalid_api_key"),
        (lambda r: httpx.Response(502, text="boom"), "tts_http_502"),
        (lambda r: httpx.Response(202, json={"job_id": "j"}) if r.method == "POST"
         else httpx.Response(200, json={"status": "failed"}), "tts_job_failed"),
        (lambda r: httpx.Response(202, json={"job_id": "j"}) if r.method == "POST"
         else httpx.Response(200, json={"status": "processing"}), "tts_timeout"),
    ],
)  # fmt: skip
def test_yarngpt_errors_become_codes_only(handler, code):
    with pytest.raises(ProviderError) as e:
        _yarn(handler).render("t", "en", "idera", 1.0)
    assert e.value.code == code and "secret" not in str(e.value)


# --- readbacks ---


def test_every_language_has_a_versioned_template():
    for lang in LANGS:
        version, text = load_template(lang)
        assert version >= 1 and "{payee}" in text and "{amount_words}" in text


def test_pidgin_readback_matches_the_prd_example():
    assert render_readback("pcm", "Bisi Ventures", 1_500_000) == (
        "Bisi Ventures dey ask for fifteen thousand naira. One five, zero zero zero. You wan approve?"
    )


def test_readback_words_and_digits_come_from_the_same_amount():
    text = render_readback("en", "Bisi Ventures", 5_100_000)
    assert "fifty one thousand" in text and "Five one, zero zero zero" in text


def test_demo_script_covers_five_languages_and_is_deduplicated():
    lines = demo_lines()
    assert len(lines) == len(set(lines))
    assert {lang for lang, _ in lines} == set(LANGS)
