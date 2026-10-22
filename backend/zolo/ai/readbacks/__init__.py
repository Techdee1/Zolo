"""Readback templates (versioned text files) filled from a stored request's fields.

The words a customer approves against are fixed templates plus bank-verified data, never freely
generated text. The consent engine owns the stored record; this only voices it.
"""

from pathlib import Path

from zolo.ai.nlu.words import digits_spoken, kobo_to_naira_words
from zolo.ai.types import Lang

_DIR = Path(__file__).parent


def load_template(lang: Lang) -> tuple[int, str]:
    """Return (version, template text) for a language."""
    version, body = 0, []
    for line in (_DIR / f"{lang}.txt").read_text(encoding="utf-8").splitlines():
        if line.startswith("# version:"):
            version = int(line.split(":", 1)[1])
        elif line.strip() and not line.startswith("#"):
            body.append(line.strip())
    if not body:
        raise ValueError(f"empty readback template for {lang}")
    return version, " ".join(body)


def render_readback(lang: Lang, payee: str, amount_kobo: int) -> str:
    _, template = load_template(lang)
    naira = amount_kobo // 100
    spoken = digits_spoken(naira)
    return template.format(
        payee=payee,
        amount_words=kobo_to_naira_words(amount_kobo),
        amount_digits_spoken=spoken[0].upper() + spoken[1:],
    )
