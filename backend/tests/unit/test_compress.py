import subprocess

from zolo.ai.stt.audio import ffmpeg_binary
from zolo.ai.tts.compress import compress_mp3


def _tone(kbps: int, channels: int) -> bytes:
    """A real mp3 to compress: two seconds of tone, stereo and 128 kbps by default."""
    cmd = [ffmpeg_binary(), "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i",
           "sine=frequency=440:duration=2", "-ac", str(channels), "-b:a", f"{kbps}k",
           "-f", "mp3", "pipe:1"]  # fmt: skip
    return subprocess.run(cmd, capture_output=True, check=True).stdout


def _info(data: bytes) -> str:
    done = subprocess.run([ffmpeg_binary(), "-i", "pipe:0"], input=data, capture_output=True)
    return done.stderr.decode()


def test_a_stereo_128_kbps_clip_becomes_mono_and_much_smaller() -> None:
    big = _tone(128, 2)
    small = compress_mp3(big)
    assert len(small) < len(big) / 2
    info = _info(small)
    assert "mono" in info and "40 kb/s" in info


def test_anything_that_is_not_audio_is_kept_as_it_was() -> None:
    junk = b"FAKE-MP3|en|idera|not really audio"
    assert compress_mp3(junk) == junk


def test_it_never_makes_a_clip_bigger() -> None:
    tiny = compress_mp3(_tone(32, 1))
    assert len(compress_mp3(tiny)) <= len(tiny)
