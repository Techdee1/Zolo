"""Render the clip set for the demo: every language, then ship it inside the image.

    python -m zolo.tools.render_clips --dry-run                # exact counts and voices, no credits
    python -m zolo.tools.render_clips                          # render what is missing (credits)
    python -m zolo.tools.render_clips --export audio_seed      # copy the set into a folder to ship

The set, in English, Pidgin, Yoruba, Hausa and Igbo:
  * the demo script lines (readbacks, voice replies, fixed phrases);
  * the fixed status lines: paid, declined, expired, processing (no amount, no name);
  * the readback for each of N2,000, N5,000, N10,000, N15,000, N20,000 and N50,000, for every seeded
    agent. If the whole set would pass 150 clips, the amounts for the non-English languages are cut
    to N5,000 and N15,000.
The primary voice (TTS_VOICE_<LANG>, default idera) is rendered for every language, and a backup
voice for English and Pidgin, so a voice can be swapped by setting TTS_VOICE_EN / TTS_VOICE_PCM.

Rendering is one clip at a time and skips anything already cached. If the provider says the quota
is used up, it stops at once and says how many are done. Prints counts only, never the words.
Clips are stored as mono mp3 at 40 kbps under the same cache key as before.
"""

import argparse
import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path

from zolo.ai.config import Settings, load_dotenv
from zolo.ai.demo_script import demo_lines
from zolo.ai.tts.base import AudioClip
from zolo.ai.tts.cache import AudioCache, cache_key
from zolo.ai.tts.compress import compress_mp3
from zolo.ai.tts.factory import RoutingTTS
from zolo.ai.types import LANGS, Lang, ProviderError
from zolo.consent.readback import build_readback
from zolo.demo import seed_data

NAIRA = 100
AMOUNTS_NAIRA = (2_000, 5_000, 10_000, 15_000, 20_000, 50_000)
TRIMMED_AMOUNTS_NAIRA = (5_000, 15_000)  # for the non-English languages if the set is too big
MAX_CLIPS = 150
RATE_LIMIT_ATTEMPTS = 8  # the provider answers RATE_LIMITED when asked too fast: wait, then go on
RATE_LIMIT_WAIT_S = 30
BACKUP_VOICES: dict[Lang, str] = {"en": "jude", "pcm": "jude"}
_PHRASES = Path(__file__).resolve().parents[1] / "ai" / "readbacks" / "status_phrases.json"


@dataclass(frozen=True)
class Clip:
    lang: Lang
    voice: str
    text: str
    group: str  # "script" | "status" | "amounts"
    backup: bool = False


def agent_names() -> list[str]:
    agents = {seed_data.BISI.id, seed_data.MAMA_CHI.id}
    return [acc.verified_name for acc in seed_data.ACCOUNTS if acc.agent_id in agents]


def status_lines() -> list[tuple[Lang, str]]:
    spec = json.loads(_PHRASES.read_text(encoding="utf-8"))["phrases"]
    return [
        (lang, spec[lang][k])
        for lang in LANGS
        for k in sorted(spec[lang])
        if not k.startswith("call_")
    ]


def call_lines() -> list[tuple[Lang, str]]:
    """The phone-approval prompts: English and Pidgin only (the call is spoken in those two)."""
    spec = json.loads(_PHRASES.read_text(encoding="utf-8"))["phrases"]
    return [
        (lang, spec[lang][k])
        for lang in ("en", "pcm")
        for k in sorted(spec[lang])
        if k.startswith("call_")
    ]


def amount_lines(trim_non_english: bool) -> list[tuple[Lang, str]]:
    out: list[tuple[Lang, str]] = []
    for lang in LANGS:
        amounts = TRIMMED_AMOUNTS_NAIRA if trim_non_english and lang != "en" else AMOUNTS_NAIRA
        for name in agent_names():
            out += [(lang, build_readback(lang, name, n * NAIRA).text) for n in amounts]
    return out


def plan(settings: Settings, trim_non_english: bool = False) -> list[Clip]:
    """Every clip to have, with the voice it is rendered in, without repeats."""
    texts: list[tuple[Lang, str, str]] = (
        [(lang, text, "script") for lang, text in demo_lines()]
        + [(lang, text, "status") for lang, text in status_lines()]
        + [(lang, text, "call") for lang, text in call_lines()]
        + [(lang, text, "amounts") for lang, text in amount_lines(trim_non_english)]
    )
    clips: dict[tuple[Lang, str, str], Clip] = {}
    for lang, text, group in texts:
        primary = settings.tts_voice_for(lang)
        clips.setdefault((lang, primary, text), Clip(lang, primary, text, group))
        backup = BACKUP_VOICES.get(lang)
        if backup and backup != primary:
            clips.setdefault((lang, backup, text), Clip(lang, backup, text, group, backup=True))
    return list(clips.values())


def choose(settings: Settings) -> tuple[list[Clip], bool]:
    """The full set, or the trimmed one if the full set is over the limit."""
    full = plan(settings)
    if len(full) <= MAX_CLIPS:
        return full, False
    return plan(settings, trim_non_english=True), True


def key_for(tts: RoutingTTS, settings: Settings, clip: Clip) -> str:
    return cache_key(tts.for_lang(clip.lang).renderer.name, clip.lang, clip.voice, clip.text)


def _counts(clips: list[Clip]) -> str:
    return ", ".join(f"{lang} {sum(c.lang == lang for c in clips)}" for lang in LANGS)


def dry_run(settings: Settings) -> None:
    clips, trimmed = choose(settings)
    tts, cache = RoutingTTS(settings), AudioCache(settings.audio_cache_dir)
    missing = [c for c in clips if cache.get(key_for(tts, settings, c)) is None]
    print(
        f"{len(clips)} clips in the set, {len(clips) - len(missing)} cached, "
        f"{len(missing)} to render"
    )
    if trimmed:
        full = plan(settings)
        print(f"the full set would be {len(full)} (over {MAX_CLIPS}): amounts for the non-English "
              f"languages cut to N5,000 and N15,000")  # fmt: skip
    print(f"per language (set): {_counts(clips)}")
    print(f"per language (to render): {_counts(missing)}")
    for label, group in (("script", "script"), ("status", "status"), ("amounts", "amounts")):
        print(f"{label}: {sum(c.group == group for c in clips)}", end="  ")
    print()
    for lang in LANGS:
        primary = settings.tts_voice_for(lang)
        backup = BACKUP_VOICES.get(lang)
        print(f"voice {lang}: primary {primary}" + (f", backup {backup}" if backup else ""))
    chars = sum(len(c.text) for c in missing)
    print(f"characters to synthesize: {chars}")


def render(settings: Settings) -> int:
    clips, _ = choose(settings)
    tts, cache = RoutingTTS(settings), AudioCache(settings.audio_cache_dir)
    todo = [c for c in clips if cache.get(key_for(tts, settings, c)) is None]
    print(f"{len(clips)} clips, {len(clips) - len(todo)} cached, {len(todo)} to render", flush=True)
    done = failed = chars = 0
    for i, clip in enumerate(todo, 1):
        t0 = time.monotonic()
        for attempt in range(1, RATE_LIMIT_ATTEMPTS + 1):
            try:
                tts.for_lang(clip.lang).prerender(clip.text, clip.lang, clip.voice)
                break
            except ProviderError as exc:
                code = exc.code.upper()
                if "QUOTA" in code:
                    print(f"[{i}/{len(todo)}] {clip.lang} QUOTA EXHAUSTED: stopping. "
                          f"{done} rendered, {len(todo) - i + 1} not attempted",
                          flush=True)  # fmt: skip
                    return 2
                if "RATE" in code and attempt < RATE_LIMIT_ATTEMPTS:
                    wait = RATE_LIMIT_WAIT_S * attempt
                    print(f"[{i}/{len(todo)}] rate limited, waiting {wait}s", flush=True)
                    time.sleep(wait)
                    continue
                failed += 1
                print(f"[{i}/{len(todo)}] {clip.lang} FAILED {exc.code}", flush=True)
                break
        else:
            continue
        if cache.get(key_for(tts, settings, clip)) is None:
            continue
        done += 1
        chars += len(clip.text)
        took = time.monotonic() - t0
        print(f"[{i}/{len(todo)}] {clip.lang} {clip.voice} ok {took:.1f}s", flush=True)
    print(f"done: {done} rendered, {failed} failed, {chars} characters", flush=True)
    return 1 if failed else 0


def export(settings: Settings, dest: Path) -> int:
    """Copy the set's cached clips into `dest`, each as mono mp3 at 40 kbps."""
    clips, _ = choose(settings)
    tts, cache = RoutingTTS(settings), AudioCache(settings.audio_cache_dir)
    dest.mkdir(parents=True, exist_ok=True)
    for old in dest.glob("*.mp3"):
        old.unlink()  # the folder is exactly the set, never a pile-up of old ones
    copied = missing = 0
    per_lang = {lang: 0 for lang in LANGS}
    size = 0
    for clip in clips:
        found = cache.get(key_for(tts, settings, clip))
        if found is None:
            missing += 1
            continue
        data = AudioClip(compress_mp3(found.data), found.mime).data
        (dest / f"{key_for(tts, settings, clip)}.mp3").write_bytes(data)
        copied += 1
        per_lang[clip.lang] += 1
        size += len(data)
    print(f"exported {copied} clips ({size / 1024:.0f} KB) to {dest}, {missing} not rendered")
    print("per language: " + ", ".join(f"{lang} {n}" for lang, n in per_lang.items()))
    return 0


def inventory(settings: Settings) -> dict[Lang, tuple[int, int]]:
    """Per language: how many of the set's clips are in the cache now, and how many the set has."""
    clips, _ = choose(settings)
    tts, cache = RoutingTTS(settings), AudioCache(settings.audio_cache_dir)
    out: dict[Lang, tuple[int, int]] = {}
    for lang in LANGS:
        mine = [c for c in clips if c.lang == lang]
        present = sum(cache.get(key_for(tts, settings, c)) is not None for c in mine)
        out[lang] = (present, len(mine))
    return out


def log_audio_inventory() -> None:
    """One line at startup so a missing clip is visible in the logs. Never stops the app."""
    log = logging.getLogger("zolo.audio")
    try:
        counts = inventory(Settings.from_env())
        summary = ", ".join(f"{lang} {have}/{want}" for lang, (have, want) in counts.items())
        have_all = sum(have for have, _ in counts.values())
        want_all = sum(want for _, want in counts.values())
        log.info(
            "audio clips present: %s (total %d/%d)", summary, have_all, want_all,
            extra={"event": "audio_inventory", "summary": summary, "total": have_all},
        )  # fmt: skip
    except Exception as exc:  # an unreadable folder must never take the API down
        failed = {"event": "audio_inventory_failed", "code": type(exc).__name__}
        log.warning("audio inventory failed", extra=failed)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="counts and voices, no credits")
    ap.add_argument("--export", type=Path, help="copy the set into this folder")
    args = ap.parse_args()
    load_dotenv()
    settings = Settings.from_env()
    if args.dry_run:
        dry_run(settings)
        return 0
    if args.export:
        return export(settings, args.export)
    return render(settings)


if __name__ == "__main__":
    raise SystemExit(main())
