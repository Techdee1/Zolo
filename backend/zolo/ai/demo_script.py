"""Expand readbacks/demo_script.json into every (lang, text) line the demo can speak."""

import json
from pathlib import Path

from zolo.ai.nlu.words import balance_words
from zolo.ai.readbacks import render_readback
from zolo.ai.replies import reply_text, static_reply_lines
from zolo.ai.types import Lang

_PATH = Path(__file__).parent / "readbacks" / "demo_script.json"


def demo_lines() -> list[tuple[Lang, str]]:
    spec = json.loads(_PATH.read_text(encoding="utf-8"))
    lines: list[tuple[Lang, str]] = []
    for lang in spec["readback_langs"]:
        for rb in spec["readbacks"]:
            lines.append((lang, render_readback(lang, rb["payee"], rb["amount_kobo"])))
    for lang, texts in spec["phrases"].items():
        lines += [(lang, t) for t in texts]
    lines += static_reply_lines()  # everything voice_turn can say without live synthesis
    return list(dict.fromkeys(lines))


_SCENARIOS = Path(__file__).parent / "readbacks" / "scenarios.json"


def scenario_lines() -> list[tuple[Lang, str]]:
    """Extra demo variants: other amounts, the two-Tundes case, and balance replies."""
    spec = json.loads(_SCENARIOS.read_text(encoding="utf-8"))
    lines: list[tuple[Lang, str]] = []
    for lang in spec["langs"]:
        for rb in spec["readbacks"]:
            lines.append((lang, render_readback(lang, rb["payee"], rb["amount_kobo"])))
        for b in spec["balances"]:
            lines.append(
                (lang, reply_text("balance", lang, amount=balance_words(b["balance_kobo"])))
            )
    return list(dict.fromkeys(lines))
