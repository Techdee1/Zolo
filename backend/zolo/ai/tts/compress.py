"""Shrink a rendered clip: mono mp3 at 40 kbps. Short spoken sentences do not need more, and the
clips are shipped inside the image and fetched over mobile data, so size matters.

The cache key does not change (it is a hash of the words, language and voice, not of the bytes).
If ffmpeg is missing or fails, the original clip is kept: a bigger clip beats no clip.
"""

import logging
import subprocess

from zolo.ai.stt.audio import ffmpeg_binary
from zolo.ai.types import ProviderError

log = logging.getLogger("zolo.ai.tts.compress")

TARGET_KBPS = 40
SAMPLE_RATE = 16_000  # speech; a lower rate than music, and what the provider already returns


def compress_mp3(data: bytes, kbps: int = TARGET_KBPS, timeout_s: float = 30.0) -> bytes:
    """The same audio as mono mp3 at `kbps`, or `data` unchanged if it cannot be converted."""
    try:
        cmd = [
            ffmpeg_binary(), "-hide_banner", "-loglevel", "error", "-i", "pipe:0", "-vn",
            "-ac", "1", "-ar", str(SAMPLE_RATE), "-b:a", f"{kbps}k", "-f", "mp3", "pipe:1",
        ]  # fmt: skip
        done = subprocess.run(cmd, input=data, capture_output=True, timeout=timeout_s, check=False)
    except (ProviderError, OSError, subprocess.TimeoutExpired):
        return data
    if done.returncode != 0 or not done.stdout:
        log.warning("clip not compressed", extra={"event": "compress_skipped"})
        return data
    return done.stdout if len(done.stdout) < len(data) else data
