"""Manual check that Spitch transcribes a clip in each language. Not run in CI.

    python -m zolo.ai.tools.stt_smoke --live [--refresh]

Uses the pre-rendered demo readbacks as audio (synthetic speech, not real customers). Transcripts
are cached per clip in var/stt_cache.json and reused unless --refresh, so a repeat run costs
nothing. At most one Spitch call per language. Without --live it only lists what it would do.
"""

import argparse
import hashlib
import json
import time
from pathlib import Path

from zolo.ai.config import Settings, load_dotenv
from zolo.ai.readbacks import render_readback
from zolo.ai.stt.spitch import SpitchSTT
from zolo.ai.tts.cache import AudioCache, cache_key
from zolo.ai.types import LANGS, ProviderError

CACHE = Path("var/stt_cache.json")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="really call Spitch (costs credits)")
    ap.add_argument("--refresh", action="store_true", help="ignore cached transcripts")
    args = ap.parse_args()
    load_dotenv()
    base = Settings.from_env()
    settings = Settings(**{**base.__dict__, "stt_live_enabled": args.live})
    audio = AudioCache(settings.audio_cache_dir)
    stt = SpitchSTT(settings)
    cache = json.loads(CACHE.read_text()) if CACHE.exists() and not args.refresh else {}

    ok = True
    for lang in LANGS:
        text = render_readback(lang, "Bisi Ventures", 1_500_000)
        clip = audio.get(cache_key("yarngpt", lang, settings.tts_voice_for(lang), text))
        if clip is None:
            print(f"{lang}: no cached clip, run prerender_demo first")
            ok = False
            continue
        key = hashlib.sha256(lang.encode() + clip.data).hexdigest()
        if key in cache:
            got, source = cache[key], "cached"
        elif not args.live:
            print(f"{lang}: would call Spitch (use --live)")
            continue
        else:
            t0 = time.monotonic()
            try:
                got = stt.transcribe(clip.data, "audio/mpeg", lang, ["Bisi Ventures"]).text
            except ProviderError as exc:
                print(f"{lang}: FAILED {exc.code}")
                ok = False
                continue
            cache[key], source = got, f"live {time.monotonic() - t0:.1f}s"
            CACHE.parent.mkdir(parents=True, exist_ok=True)
            CACHE.write_text(json.dumps(cache))
        print(f"{lang} [{source}]\n  said: {text}\n  heard: {got}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
