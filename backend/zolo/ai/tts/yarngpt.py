"""YarnGPT text to speech (hosted API only; the docs mention no self-hosting).

Job flow: POST /api/v1/tts (needs Idempotency-Key) -> poll GET /api/v1/status/{job_id} until
audio_url appears -> download the signed link (without our key). There is no Pidgin language
code, so Pidgin text is sent with target_language "en". No speed parameter exists.
Retention of TTS output is unstated by the docs.
"""

import hashlib
import time
from collections.abc import Callable

import httpx

from zolo.ai.config import api_key
from zolo.ai.tts.base import AudioClip
from zolo.ai.types import Lang, ProviderError

BASE_URL = "https://api.yarngpt.ai"
TARGET_LANGUAGE: dict[Lang, str] = {"en": "en", "pcm": "en", "yo": "yo", "ha": "ha", "ig": "ig"}
POLL_INTERVAL_S = 0.3


class YarnGPTRenderer:
    name = "yarngpt"

    def __init__(
        self,
        client: httpx.Client | None = None,
        key: str | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._client = client or httpx.Client(base_url=BASE_URL)
        self._key = key
        self._sleep, self._clock = sleep, clock

    def _auth(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._key or api_key('YARNGPT_API_KEY')}"}

    def render(self, text: str, lang: Lang, voice: str, timeout_s: float) -> AudioClip:
        deadline = self._clock() + timeout_s

        def remaining() -> float:
            return max(0.1, deadline - self._clock())

        try:
            # Same text, voice and language always gets the same job, so a retry never double-bills.
            idem = hashlib.sha256(f"{lang}|{voice}|{text}".encode()).hexdigest()[:48]
            r = self._client.post(
                "/api/v1/tts",
                headers={**self._auth(), "Idempotency-Key": idem},
                json={
                    "text": text,
                    "voice": voice,
                    "output_format": "mp3",
                    "target_language": TARGET_LANGUAGE[lang],
                },
                timeout=remaining(),
            )
            if r.status_code != 202:
                raise ProviderError(_error_code(r))
            job_id = r.json()["job_id"]
            while True:
                s = self._client.get(
                    f"/api/v1/status/{job_id}", headers=self._auth(), timeout=remaining()
                )
                if s.status_code != 200:
                    raise ProviderError(_error_code(s))
                body = s.json()
                if body.get("status") == "failed":
                    raise ProviderError("tts_job_failed")
                if body.get("audio_url"):
                    # Signed link on another host: never send our API key to it.
                    a = httpx.get(body["audio_url"], timeout=remaining(), follow_redirects=True)
                    if a.status_code != 200 or not a.content:
                        raise ProviderError("tts_download_failed")
                    return AudioClip(a.content, "audio/mpeg")
                if self._clock() >= deadline:
                    raise ProviderError("tts_timeout")
                self._sleep(POLL_INTERVAL_S)
        except ProviderError:
            raise
        except httpx.TimeoutException:
            raise ProviderError("tts_timeout") from None
        except Exception:
            raise ProviderError("tts_error") from None  # never carry provider text


def _error_code(r: httpx.Response) -> str:
    try:
        code = r.json()["error"]["code"]
        return f"tts_{str(code)[:40]}"
    except Exception:
        return f"tts_http_{r.status_code}"
