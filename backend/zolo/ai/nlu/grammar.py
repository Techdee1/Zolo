"""Deterministic understanding of "send X to Y" and "check balance" (English and Pidgin).

Always runs, even when the LLM agent is on (Phase 2). It only reads; it never decides.
Yoruba, Hausa and Igbo verbs are not here: they need native-speaker review (Phase 3), and until
then those languages use English money and command words.
"""

import re
from dataclasses import dataclass
from typing import Literal

from zolo.ai.nlu.amount import AmountResult, parse_amount
from zolo.ai.nlu.banks import extract_bank, normalise

Intent = Literal["send", "balance", "unknown"]

_DIGIT_WORDS = {
    w: str(i)
    for i, w in enumerate(
        ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"]
    )
} | {"oh": "0"}

_SEND_VERB = re.compile(r"\b(send|sen|transfer|pay|dash|wire|move)\b")
_GIVE = re.compile(r"\bgive\b")
_BALANCE = re.compile(
    r"\bbalance\b"
    r"|\bhow much\b.*\b(get|have|remain|remains|left|dey)\b"
    r"|\bwetin\b.*\b(dey|get)\b.*\b(account|money)\b"
)
# Words that carry the command, not the recipient. Removed to leave the recipient phrase.
_COMMAND_WORDS = {
    "send", "sen", "transfer", "pay", "dash", "wire", "move", "give", "abeg", "please", "pls",
    "i", "wan", "want", "to", "make", "let", "me", "go", "money", "naira", "ngn", "some", "of",
    "kindly", "now", "cash", "am", "na", "for", "inside", "enter", "put", "drop", "wey", "dey",
    "account", "the", "bank", "can", "you", "us", "a", "an",
}  # fmt: skip
# "for" and "bank" stay when they introduce or are part of a bank name; see _recipient_phrase.


@dataclass(frozen=True)
class Parsed:
    intent: Intent
    amount: AmountResult | None = None
    recipient_phrase: str | None = None
    account_number: str | None = None
    bank: str | None = None


def extract_account_number(text: str) -> tuple[str | None, str]:
    """Pull a 10-digit account number out of the text, typed or spoken digit by digit.

    Returns (digits or None, text with the number replaced by a space).
    """
    m = re.search(r"(?<!\d)(?:\d[\s-]?){9}\d(?!\d)", text)
    if m:
        return re.sub(r"\D", "", m.group()), text[: m.start()] + " " + text[m.end() :]

    words = list(re.finditer(r"[A-Za-z]+|\d", text))
    run: list[re.Match[str]] = []
    for m in [*words, None]:
        if m is not None and m.group().lower() in _DIGIT_WORDS | {str(i): "" for i in range(10)}:
            run.append(m)
            continue
        if len(run) == 10:
            digits = "".join(_DIGIT_WORDS.get(r.group().lower(), r.group()) for r in run)
            return digits, text[: run[0].start()] + " " + text[run[-1].end() :]
        run = []
    return None, text


def _starts_bank(tokens: list[str]) -> bool:
    """True when the tokens begin with a bank name."""
    return any(extract_bank(tokens[:n])[0] is not None for n in (1, 2, 3))


def _recipient_phrase(text: str, bank: str | None) -> str | None:
    tokens = normalise(text).split()
    kept: list[str] = []
    for i, tok in enumerate(tokens):
        if tok in _COMMAND_WORDS:
            # keep "for <bank>" so the matcher can see the bank; drop every other command word
            if tok == "for" and bank is not None and _starts_bank(tokens[i + 1 :]):
                kept.append(tok)
            continue
        kept.append(tok)
    phrase = " ".join(kept).strip()
    return phrase or None


def parse_utterance(text: str) -> Parsed:
    low = text.casefold()
    wants_balance = bool(_BALANCE.search(low))
    account, masked = extract_account_number(text)
    amount = parse_amount(masked)
    amount_found = amount.kobo is not None
    wants_send = bool(_SEND_VERB.search(low)) or (bool(_GIVE.search(low)) and amount_found)

    if wants_balance and not wants_send:
        return Parsed("balance")
    if wants_send and not wants_balance:
        # Remove the amount words before taking the recipient phrase.
        rest = masked
        if amount.span is not None:
            rest = masked[: amount.span[0]] + " " + masked[amount.span[1] :]
        bank, _ = extract_bank(normalise(rest).split())
        return Parsed(
            "send",
            amount=amount,
            recipient_phrase=_recipient_phrase(rest, bank),
            account_number=account,
            bank=bank,
        )
    return Parsed("unknown")
