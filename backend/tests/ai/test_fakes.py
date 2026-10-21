import pytest

from zolo.ai.stt.fake import FakeSTT
from zolo.ai.tts.fake import FakeTTS
from zolo.ai.types import ProviderError


def test_fake_stt_echoes_text():
    t = FakeSTT().transcribe(b"check balance", "audio/webm", "en")
    assert t.text == "check balance" and t.confidence == 0.95


def test_fake_stt_can_fail():
    with pytest.raises(ProviderError) as e:
        FakeSTT(fail_with="timeout").transcribe(b"x", "audio/webm", "en")
    assert e.value.code == "timeout"


def test_fake_tts_is_deterministic():
    a = FakeTTS().synthesize("hello", "en", "v1")
    assert a == FakeTTS().synthesize("hello", "en", "v1")
    assert a != FakeTTS().synthesize("hello", "pcm", "v1")
