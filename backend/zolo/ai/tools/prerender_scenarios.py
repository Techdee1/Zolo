"""Pre-render extra demo variants (other amounts, the two-Tundes case, balance checks).

    python -m zolo.ai.tools.prerender_scenarios [--dry-run]

Lines come from readbacks/scenarios.json. Anything already cached is skipped, so only new text
costs a YarnGPT render. Prints counts and timings, never the text.
"""

import argparse
import time

from zolo.ai.config import Settings, load_dotenv
from zolo.ai.demo_script import scenario_lines
from zolo.ai.tts.cache import AudioCache, cache_key
from zolo.ai.tts.factory import RoutingTTS
from zolo.ai.types import ProviderError


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="count what would be rendered")
    args = ap.parse_args()
    load_dotenv()
    settings = Settings.from_env()
    tts, cache = RoutingTTS(settings), AudioCache(settings.audio_cache_dir)

    lines = scenario_lines()
    todo = [
        (lang, text)
        for lang, text in lines
        if cache.get(
            cache_key(tts.for_lang(lang).renderer.name, lang, settings.tts_voice_for(lang), text)
        )
        is None
    ]
    print(f"{len(lines)} scenario lines, {len(lines) - len(todo)} cached, {len(todo)} to render")
    if args.dry_run:
        return 0

    failed = 0
    for i, (lang, text) in enumerate(todo, 1):
        t0 = time.monotonic()
        try:
            tts.for_lang(lang).prerender(text, lang, settings.tts_voice_for(lang))
            print(f"[{i}/{len(todo)}] {lang} ok {time.monotonic() - t0:.1f}s")
        except ProviderError as exc:
            failed += 1
            print(f"[{i}/{len(todo)}] {lang} FAILED {exc.code}")
    print(f"done, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
