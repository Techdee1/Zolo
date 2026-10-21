"""Pre-render every demo script line into the audio cache so the stage demo plays from cache.

    python -m zolo.ai.tools.prerender_demo [--dry-run] [--langs en,pcm]

Already-cached lines are skipped, so it is safe to re-run and only spends credits on new text.
Prints counts and timings only, never the text.
"""

import argparse
import time

from zolo.ai.config import Settings, load_dotenv
from zolo.ai.demo_script import demo_lines
from zolo.ai.tts.cache import AudioCache, cache_key
from zolo.ai.tts.factory import RoutingTTS
from zolo.ai.types import ProviderError


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="count what would be rendered")
    ap.add_argument("--langs", help="comma separated subset, e.g. en,pcm")
    args = ap.parse_args()

    load_dotenv()
    settings = Settings.from_env()
    only = set(args.langs.split(",")) if args.langs else None
    lines = [(lang, text) for lang, text in demo_lines() if only is None or lang in only]
    tts, cache = RoutingTTS(settings), AudioCache(settings.audio_cache_dir)

    todo = []
    for lang, text in lines:
        provider = tts.for_lang(lang).renderer.name
        if cache.get(cache_key(provider, lang, settings.tts_voice_for(lang), text)) is None:
            todo.append((lang, text))
    print(f"{len(lines)} lines, {len(lines) - len(todo)} cached, {len(todo)} to render")
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
