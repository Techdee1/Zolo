"""The fixed lines the call speaks. The words live in the AI package's phrase file, so the same
clip tool that renders the other fixed lines renders these, and the same cache serves them."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from zolo.consent.audio import AudioLookup

CallLang = Literal["en", "pcm"]
_FILE = Path(__file__).resolve().parents[1] / "ai" / "readbacks" / "status_phrases.json"
_PHRASES: dict[str, dict[str, str]] = json.loads(_FILE.read_text("utf-8"))["phrases"]


@dataclass(frozen=True)
class Prompt:
    key: str
    text: str
    audio_url: str | None  # None when there is no recording; the app then speaks the text itself


def prompt(key: str, lang: CallLang, audio: AudioLookup) -> Prompt:
    text = _PHRASES[lang][f"call_{key}"]
    return Prompt(key, text, audio.audio_url(text, lang))


def known_keys(lang: CallLang) -> set[str]:
    return {k.removeprefix("call_") for k in _PHRASES[lang] if k.startswith("call_")}


Expects = Literal["choice", "pin", "none"]
