"""Pre-render the readback for the amounts people actually ask for, so the first listen is instant.

    python -m zolo.tools.prerender_amounts [--dry-run] [--langs en,pcm] [--max-naira 100000]
    python -m zolo.tools.prerender_amounts --export audio_seed      # copy the clips into a folder

Every seeded agent, in English and Pidgin, for a grid of amounts: every N500 up to N10,000, every
N1,000 up to N20,000, then every N5,000 up to the cap. Any other amount is still rendered in the
background when the agent asks (AUDIO_PRERENDER_ON_CREATE=true); this just warms the cache.
Already-cached lines are skipped, so it only spends credits on new text. Prints counts only.
"""

import argparse
import time
from pathlib import Path

from zolo.ai.config import Settings, load_dotenv
from zolo.ai.tts.cache import AudioCache, cache_key
from zolo.ai.tts.factory import RoutingTTS
from zolo.ai.types import Lang, ProviderError
from zolo.consent.readback import READBACK_LANGS, build_readback
from zolo.demo import seed_data

NAIRA = 100


def amount_grid(max_naira: int = 100_000) -> list[int]:
    """Naira amounts, in order, without repeats."""
    grid = set(range(500, 10_001, 500)) | set(range(1_000, 20_001, 1_000))
    grid |= set(range(5_000, max_naira + 1, 5_000))
    return sorted(n for n in grid if n <= max_naira)


def agent_names() -> list[str]:
    agents = {seed_data.BISI.id, seed_data.MAMA_CHI.id}
    return [acc.verified_name for acc in seed_data.ACCOUNTS if acc.agent_id in agents]


def lines(langs: set[str] | None, max_naira: int) -> list[tuple[Lang, str]]:
    out: list[tuple[Lang, str]] = []
    for lang in READBACK_LANGS:
        if langs is not None and lang not in langs:
            continue
        for name in agent_names():
            for naira in amount_grid(max_naira):
                out.append((lang, build_readback(lang, name, naira * NAIRA).text))
    return list(dict.fromkeys(out))


def export(dest: Path, langs: set[str] | None, max_naira: int) -> int:
    """Copy the cached clips for this grid into `dest` (to ship them inside the image)."""
    settings = Settings.from_env()
    tts, cache = RoutingTTS(settings), AudioCache(settings.audio_cache_dir)
    dest.mkdir(parents=True, exist_ok=True)
    copied = missing = 0
    for lang, text in lines(langs, max_naira):
        provider = tts.for_lang(lang).renderer.name
        key = cache_key(provider, lang, settings.tts_voice_for(lang), text)
        clip = cache.get(key)
        if clip is None:
            missing += 1
            continue
        (dest / f"{key}.mp3").write_bytes(clip.data)
        copied += 1
    print(f"exported {copied} clips to {dest}, {missing} not rendered yet")
    return 1 if missing else 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="count what would be rendered")
    ap.add_argument("--langs", help="comma separated subset, e.g. en,pcm")
    ap.add_argument("--max-naira", type=int, default=100_000)
    ap.add_argument("--export", type=Path, help="copy the grid's cached clips into this folder")
    args = ap.parse_args()

    load_dotenv()
    if args.export:
        wanted_langs = set(args.langs.split(",")) if args.langs else None
        return export(args.export, wanted_langs, args.max_naira)
    settings = Settings.from_env()
    wanted = set(args.langs.split(",")) if args.langs else None
    todo_all = lines(wanted, args.max_naira)
    tts, cache = RoutingTTS(settings), AudioCache(settings.audio_cache_dir)

    todo = []
    for lang, text in todo_all:
        provider = tts.for_lang(lang).renderer.name
        if cache.get(cache_key(provider, lang, settings.tts_voice_for(lang), text)) is None:
            todo.append((lang, text))
    print(f"{len(todo_all)} lines, {len(todo_all) - len(todo)} cached, {len(todo)} to render")
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
