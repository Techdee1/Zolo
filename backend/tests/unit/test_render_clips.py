from zolo.ai.config import Settings
from zolo.ai.types import LANGS
from zolo.consent.readback import build_readback
from zolo.tools.render_clips import (
    AMOUNTS_NAIRA,
    BACKUP_VOICES,
    MAX_CLIPS,
    TRIMMED_AMOUNTS_NAIRA,
    agent_names,
    choose,
    plan,
    status_lines,
)

SETTINGS = Settings.from_env()


def test_the_set_covers_all_five_languages() -> None:
    clips, _ = choose(SETTINGS)
    assert {c.lang for c in clips} == set(LANGS)


def test_every_language_has_a_primary_voice_and_only_english_and_pidgin_have_a_backup() -> None:
    clips, _ = choose(SETTINGS)
    for lang in LANGS:
        voices = {c.voice for c in clips if c.lang == lang}
        assert SETTINGS.tts_voice_for(lang) in voices
        if lang in BACKUP_VOICES:
            assert voices == {SETTINGS.tts_voice_for(lang), BACKUP_VOICES[lang]}
        else:
            assert voices == {SETTINGS.tts_voice_for(lang)}


def test_nothing_is_listed_twice() -> None:
    clips, _ = choose(SETTINGS)
    keys = [(c.lang, c.voice, c.text) for c in clips]
    assert len(keys) == len(set(keys))


def test_the_status_lines_have_no_amount_and_no_name() -> None:
    lines = status_lines()
    assert len(lines) == 4 * len(LANGS)  # paid, declined, expired, processing in each language
    for _, text in lines:
        assert not any(ch.isdigit() for ch in text) and "₦" not in text
        assert not any(name.split()[0].lower() in text.lower() for name in agent_names())


def test_over_the_limit_the_non_english_amounts_are_cut_to_5000_and_15000() -> None:
    full = plan(SETTINGS)
    assert len(full) > MAX_CLIPS  # six amounts in five languages is too many
    clips, trimmed = choose(SETTINGS)
    assert trimmed and len(clips) < len(full)
    texts = {(c.lang, c.text) for c in clips}

    def readbacks(lang: str, amounts: tuple[int, ...]) -> set[tuple[str, str]]:
        return {
            (lang, build_readback(lang, name, n * 100).text)  # type: ignore[arg-type]
            for name in agent_names()
            for n in amounts
        }

    assert readbacks("en", AMOUNTS_NAIRA) <= texts  # English keeps all six amounts
    for lang in ("pcm", "yo", "ha", "ig"):  # Pidgin counts as non-English: it is cut too
        assert readbacks(lang, TRIMMED_AMOUNTS_NAIRA) <= texts
        assert not readbacks(lang, (2_000, 10_000, 20_000, 50_000)) & texts  # cut


def test_the_amounts_are_the_requested_ones() -> None:
    assert AMOUNTS_NAIRA == (2_000, 5_000, 10_000, 15_000, 20_000, 50_000)
    assert TRIMMED_AMOUNTS_NAIRA == (5_000, 15_000)


def test_what_ships_is_exactly_what_the_set_asks_for() -> None:
    """Every clip in audio_seed is one the set names (nothing stray), in the primary or backup voice."""
    from pathlib import Path

    from zolo.ai.tts.cache import cache_key
    from zolo.tools.render_clips import plan

    seed = Path(__file__).resolve().parents[2] / "audio_seed"
    shipped = {p.stem for p in seed.glob("*.mp3")} if seed.exists() else set()
    if not shipped:
        return  # nothing exported yet
    wanted = {cache_key("yarngpt", c.lang, c.voice, c.text) for c in plan(SETTINGS, True)}
    wanted |= {cache_key("yarngpt", c.lang, c.voice, c.text) for c in plan(SETTINGS)}
    assert shipped <= wanted, f"{len(shipped - wanted)} stray clips"
