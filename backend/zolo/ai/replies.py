"""Spoken replies (versioned file). Static replies are pre-rendered; fixed text only."""

import json
from pathlib import Path

from zolo.ai.types import Lang

_PATH = Path(__file__).parent / "readbacks" / "replies.json"
_SPEC = json.loads(_PATH.read_text(encoding="utf-8"))
REPLIES: dict[str, dict[str, str]] = _SPEC["replies"]
DYNAMIC: set[str] = set(_SPEC["dynamic"])


def reply_text(key: str, lang: Lang, **fmt: str) -> str:
    by_lang = REPLIES[key]
    return by_lang.get(lang, by_lang["en"]).format(**fmt)


def static_reply_lines() -> list[tuple[Lang, str]]:
    return [
        (lang, text)  # type: ignore[misc]
        for key, by_lang in REPLIES.items()
        if key not in DYNAMIC
        for lang, text in by_lang.items()
    ]
