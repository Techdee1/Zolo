"""Normalise whatever the browser recorded to 16 kHz mono wav with ffmpeg.

Chrome sends webm/opus, Safari mp4, Firefox ogg. Spitch accepts mp3, wav, m4a and ogg only, so
everything is converted. Audio goes through pipes (or a short-lived temp file for formats ffmpeg
cannot read from a pipe) and is never kept.
"""

import io
import os
import shutil
import subprocess
import tempfile
import wave

from zolo.ai.types import ProviderError

MAX_INPUT_BYTES = 8 * 1024 * 1024
MAX_SECONDS = 15  # the app records at most 15 seconds
_ARGS = ["-hide_banner", "-loglevel", "error", "-vn", "-t", str(MAX_SECONDS),
         "-ac", "1", "-ar", "16000", "-f", "s16le"]  # fmt: skip


def ffmpeg_binary() -> str:
    explicit = os.environ.get("FFMPEG_BIN")
    if explicit:
        return explicit
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:  # dev and CI: the bundled binary from imageio-ffmpeg
        import imageio_ffmpeg

        return str(imageio_ffmpeg.get_ffmpeg_exe())
    except Exception as exc:
        raise ProviderError("ffmpeg_missing") from exc


def _run(cmd: list[str], data: bytes | None, timeout: float) -> bytes:
    try:
        p = subprocess.run(cmd, input=data, capture_output=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired as exc:
        raise ProviderError("audio_convert_timeout") from exc
    if p.returncode != 0 or not p.stdout:
        raise ProviderError("audio_convert_failed")
    return p.stdout


def _wrap_wav(pcm: bytes) -> bytes:
    # ffmpeg cannot seek back to fix a wav header on a pipe, so it emits raw PCM and we wrap it.
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16000)
        w.writeframes(pcm)
    return buf.getvalue()


def to_wav_16k_mono(audio: bytes, timeout: float = 5.0) -> bytes:
    if not audio:
        raise ProviderError("audio_empty")
    if len(audio) > MAX_INPUT_BYTES:
        raise ProviderError("audio_too_large")
    ff = ffmpeg_binary()
    try:
        return _wrap_wav(_run([ff, "-i", "pipe:0", *_ARGS, "pipe:1"], audio, timeout))
    except ProviderError as first:
        if first.code == "audio_convert_timeout":
            raise
    # mp4 with the index at the end cannot be read from a pipe: use a short-lived file
    with tempfile.TemporaryDirectory(dir="/dev/shm" if os.path.isdir("/dev/shm") else None) as d:
        src = os.path.join(d, "in")
        with open(src, "wb") as f:
            f.write(audio)
        return _wrap_wav(_run([ff, "-i", src, *_ARGS, "pipe:1"], None, timeout))
