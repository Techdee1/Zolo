import threading

from zolo.ai.config import Settings
from zolo.ai.readbacks import render_readback
from zolo.ai.tts.base import AudioClip
from zolo.ai.tts.cache import AudioCache, cache_key
from zolo.ai.tts.factory import RoutingTTS
from zolo.ai.tts.fake import FakeRenderer
from zolo.ai.tts.readback import ReadbackService
from zolo.ai.types import LANGS


class GatedRenderer(FakeRenderer):
    """Renders only when the test opens the gate, like a slow provider."""

    def __init__(self):
        super().__init__()
        self.gate = threading.Event()

    def render(self, text, lang, voice, timeout_s):
        self.gate.wait(5)
        return super().render(text, lang, voice, timeout_s)


def make(tmp_path, renderer=None, live=True, clock=None):
    settings = Settings(
        tts_live_enabled=live, audio_cache_dir=tmp_path,
        tts_providers={lang: "fake" for lang in LANGS}, tts_voices={lang: "v" for lang in LANGS},
    )  # fmt: skip
    r = renderer or FakeRenderer()
    kwargs = {"clock": clock} if clock else {}
    return ReadbackService(RoutingTTS(settings, {"fake": r, "yarngpt": r}), **kwargs), r, settings


def test_cached_audio_is_returned_at_once_and_nothing_is_rendered(tmp_path):
    svc, r, _ = make(tmp_path)
    AudioCache(tmp_path).put(cache_key("fake", "en", "v", "Hello there"), AudioClip(b"mp3"))
    out = svc.get("Hello there", "en")
    assert out.status == "ready" and out.audio_url.startswith("/voice/audio/")
    assert out.device_speech_after_s is None and r.calls == 0


def test_miss_returns_text_now_then_audio_fills_the_cache(tmp_path):
    r = GatedRenderer()
    svc, _, _ = make(tmp_path, r)
    first = svc.get("Please wait", "en")
    assert first.status == "rendering" and first.audio_url is None and first.text == "Please wait"
    assert first.poll_url and first.device_speech_after_s == 2.0
    r.gate.set()
    svc.wait_idle()
    second = svc.get("Please wait", "en")
    assert second.status == "ready" and second.audio_url == first.poll_url and r.calls == 1


def test_english_gets_the_device_speech_flag_others_do_not(tmp_path):
    r = GatedRenderer()
    svc, _, _ = make(tmp_path, r)
    assert svc.get("x one", "en").device_speech_after_s == 2.0
    for lang in ("pcm", "yo", "ha", "ig"):
        out = svc.get("x one", lang)
        assert out.status == "rendering" and out.device_speech_after_s is None
    r.gate.set()
    svc.wait_idle()


def test_live_off_gives_text_only_and_english_speaks_it_on_device_immediately(tmp_path):
    svc, r, _ = make(tmp_path, live=False)
    en, pcm = svc.get("Nothing cached", "en"), svc.get("Nothing cached", "pcm")
    assert (en.status, en.device_speech_after_s) == ("text_only", 0.0)
    assert (pcm.status, pcm.device_speech_after_s) == ("text_only", None)
    assert r.calls == 0


def test_the_same_line_is_never_rendered_twice_at_once(tmp_path):
    r = GatedRenderer()
    svc, _, _ = make(tmp_path, r)
    for _ in range(5):
        svc.get("Same line", "en")
    r.gate.set()
    svc.wait_idle()
    assert r.calls == 1


def test_failed_render_is_not_retried_for_a_minute(tmp_path):
    now = [0.0]
    r = FakeRenderer(fail_with="tts_timeout")
    svc, _, _ = make(tmp_path, r, clock=lambda: now[0])
    svc.get("Flaky line", "en")
    svc.wait_idle()
    assert r.calls == 1
    out = svc.get("Flaky line", "en")
    assert out.status == "text_only" and r.calls == 1  # cooling down: no credits burned
    now[0] = 61.0
    r.fail_with = None
    svc.get("Flaky line", "en")
    svc.wait_idle()
    assert r.calls == 2 and svc.get("Flaky line", "en").status == "ready"


def test_wait_s_returns_audio_when_it_arrives_in_time(tmp_path):
    svc, _, _ = make(tmp_path)
    assert svc.get("Quick line", "en", wait_s=2.0).status == "ready"


def test_a_slow_provider_does_not_block_past_wait_s(tmp_path):
    r = GatedRenderer()
    svc, _, _ = make(tmp_path, r)
    assert svc.get("Slow line", "en", wait_s=0.05).status == "rendering"
    r.gate.set()
    svc.wait_idle()


def test_readback_for_builds_the_text_from_the_template(tmp_path):
    svc, _, _ = make(tmp_path)
    out = svc.readback_for("pcm", "Bisi Ventures", 1_500_000)
    assert out.text == render_readback("pcm", "Bisi Ventures", 1_500_000)
    assert "fifteen thousand" in out.text


def test_to_dict_is_json_ready(tmp_path):
    import json

    svc, _, _ = make(tmp_path, live=False)
    json.dumps(svc.get("x one", "en").to_dict())
