import io
import wave
from pathlib import Path
from types import SimpleNamespace

import pytest

from zolo.ai.config import Settings
from zolo.ai.resilience import CircuitBreaker
from zolo.ai.stt.audio import to_wav_16k_mono
from zolo.ai.stt.spitch import SpitchSTT
from zolo.ai.types import ProviderError
from zolo.ai.usage import count_call

FIX = Path(__file__).parent / "fixtures"


@pytest.mark.parametrize("name", ["fixture.webm", "fixture.mp4", "fixture.ogg"])
def test_every_browser_format_becomes_16k_mono_wav(name):
    wav = to_wav_16k_mono((FIX / name).read_bytes())
    with wave.open(io.BytesIO(wav)) as w:
        assert (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (16000, 1, 2)
        assert 0.8 < w.getnframes() / 16000 < 1.3


def test_bad_audio_is_a_provider_error_with_a_code_only():
    for bad in (b"", b"not audio at all" * 100):
        with pytest.raises(ProviderError) as e:
            to_wav_16k_mono(bad)
        assert e.value.code in ("audio_empty", "audio_convert_failed")


def test_clips_are_capped_at_15_seconds(tmp_path):
    import subprocess

    from zolo.ai.stt.audio import ffmpeg_binary

    long = subprocess.run(
        [ffmpeg_binary(), "-loglevel", "error", "-f", "lavfi", "-i", "sine=duration=30",
         "-f", "ogg", "-c:a", "libvorbis", "pipe:1"],
        capture_output=True, check=True,
    ).stdout  # fmt: skip
    with wave.open(io.BytesIO(to_wav_16k_mono(long))) as w:
        assert w.getnframes() / 16000 <= 15.1


class _FakeSpitchClient:
    def __init__(self, text="send 15k to my sister", fail=None):
        self.calls = []
        self.speech = SimpleNamespace(transcribe=self._t)
        self.text, self.fail = text, fail

    def _t(self, **kw):
        self.calls.append(kw)
        if self.fail:
            raise self.fail
        return SimpleNamespace(text=self.text)


def _settings(tmp_path, live=True):
    return Settings(stt_live_enabled=live, stt_call_count_file=tmp_path / "c.json")


def test_spitch_wrapper_converts_maps_language_and_has_no_confidence(tmp_path):
    client = _FakeSpitchClient()
    stt = SpitchSTT(_settings(tmp_path), client=client)
    t = stt.transcribe((FIX / "fixture.webm").read_bytes(), "audio/webm", "pcm", ["Tunde"])
    assert t.text == "send 15k to my sister" and t.confidence is None
    call = client.calls[0]
    assert call["language"] == "en"  # Pidgin goes through the English model
    assert call["content"][:4] == b"RIFF"  # converted to wav
    assert "Tunde" in call["special_words"] and "naira" in call["special_words"]


def test_stt_disabled_never_calls_spitch(tmp_path):
    client = _FakeSpitchClient()
    with pytest.raises(ProviderError) as e:
        SpitchSTT(_settings(tmp_path, live=False), client=client).transcribe(b"x", "a", "en")
    assert e.value.code == "stt_disabled" and client.calls == []


def test_provider_failure_carries_no_provider_text(tmp_path):
    client = _FakeSpitchClient(fail=RuntimeError("secret transcript text"))
    with pytest.raises(ProviderError) as e:
        SpitchSTT(_settings(tmp_path), client=client).transcribe(
            (FIX / "fixture.ogg").read_bytes(), "audio/ogg", "en"
        )
    assert e.value.code == "stt_error" and "secret" not in str(e.value)
    assert e.value.__cause__ is None


def test_call_count_is_counts_only(tmp_path):
    client = _FakeSpitchClient()
    stt = SpitchSTT(_settings(tmp_path), client=client)
    for _ in range(2):
        stt.transcribe((FIX / "fixture.ogg").read_bytes(), "audio/ogg", "en")
    text = (tmp_path / "c.json").read_text()
    assert '"spitch": 2' in text and "send" not in text
    assert count_call(tmp_path / "c.json", "spitch") == 3


def test_circuit_breaker_opens_after_three_failures_and_recovers():
    now = [0.0]
    cb = CircuitBreaker(clock=lambda: now[0])
    cb.record_failure()
    cb.record_failure()
    assert not cb.is_open
    cb.record_failure()
    assert cb.is_open
    now[0] = 61
    assert not cb.is_open
    cb.record_failure()
    cb.record_success()
    cb.record_failure()
    cb.record_failure()
    assert not cb.is_open  # a success resets the streak
