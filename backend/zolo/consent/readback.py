"""Readback text: fixed templates (en, pcm, yo, ha, ig) filled from the stored request row.

What the customer hears and what the passkey signs both come from the same row, read once.
The wording lives in the AI package's versioned template files so the pre-rendered audio and
the text on screen are always the same words.
"""

from dataclasses import dataclass

from zolo.ai.nlu.words import kobo_to_naira_words
from zolo.ai.readbacks import render_readback
from zolo.ai.types import Lang

READBACK_LANGS: tuple[Lang, ...] = ("en", "pcm", "yo", "ha", "ig")
# English and Pidgin always have a voice if one can be rendered. Yoruba, Hausa and Igbo are offered
# only when their exact clip already exists: otherwise the customer gets the English readback and a
# field saying so, because a screen reader would mispronounce them. See ConsentService.get_readback.
CLIP_ONLY_LANGS: tuple[Lang, ...] = ("yo", "ha", "ig")
FALLBACK_LANG: Lang = "en"


@dataclass(frozen=True)
class ReadbackText:
    text: str
    lang: Lang
    amount_words: str
    payee_name: str  # as spoken: "Bisi Ventures", not the bank's "BISI VENTURES"


def spoken_name(verified_name: str) -> str:
    """Banks send capitals ("BISI VENTURES"); speech and pre-rendered audio say "Bisi Ventures"."""
    return verified_name.title()


def readback_lang(value: str) -> Lang | None:
    """The language if readbacks support it, else None."""
    return next((lang for lang in READBACK_LANGS if lang == value), None)


def build_readback(lang: Lang, verified_name: str, amount_kobo: int) -> ReadbackText:
    if lang not in READBACK_LANGS:
        raise ValueError(f"readback language not supported: {lang}")
    name = spoken_name(verified_name)
    return ReadbackText(
        text=render_readback(lang, name, amount_kobo),
        lang=lang,
        amount_words=kobo_to_naira_words(amount_kobo),
        payee_name=name,
    )
