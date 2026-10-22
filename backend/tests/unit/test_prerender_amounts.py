from zolo.tools.prerender_amounts import agent_names, amount_grid, lines


def test_the_grid_covers_the_amounts_people_ask_for_and_stops_at_the_cap() -> None:
    grid = amount_grid()
    assert grid[0] == 500 and grid[-1] == 100_000
    assert {5_000, 15_000, 51_000 - 1_000, 20_000, 100_000} <= set(grid)
    assert grid == sorted(set(grid))
    assert max(amount_grid(30_000)) == 30_000


def test_it_covers_every_seeded_agent_in_both_readback_languages() -> None:
    assert agent_names() == ["BISI VENTURES", "MAMA CHI STORES"]
    all_lines = lines(None, 100_000)
    assert len({lang for lang, _ in all_lines}) == 2
    texts = [t for _, t in all_lines]
    assert any(t.startswith("Bisi Ventures dey ask for fifteen thousand naira") for t in texts)
    assert any(t.startswith("Mama Chi Stores is asking for five hundred naira") for t in texts)
    assert len(texts) == len(set(texts))  # no sentence is rendered twice


def test_it_can_be_limited_to_one_language() -> None:
    assert {lang for lang, _ in lines({"pcm"}, 20_000)} == {"pcm"}


def test_the_shipped_clips_are_named_by_the_keys_the_readback_looks_up(tmp_path) -> None:  # type: ignore[no-untyped-def]
    """Every clip in audio_seed must be one the grid would ask for, so nothing stray ships."""
    from pathlib import Path

    from zolo.ai.config import Settings
    from zolo.ai.tts.cache import cache_key
    from zolo.tools.prerender_amounts import lines

    seed = Path(__file__).resolve().parents[2] / "audio_seed"
    if not seed.exists():
        return  # the folder is made by `--export`; before that there is nothing to check
    settings = Settings.from_env()
    wanted = {
        cache_key(settings.tts_provider_for(lang), lang, settings.tts_voice_for(lang), text)
        for lang, text in lines(None, 100_000)
    }
    shipped = {p.stem for p in seed.glob("*.mp3")}
    assert shipped <= wanted, f"{len(shipped - wanted)} clips are not in the grid"
