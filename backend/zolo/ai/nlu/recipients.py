"""Fuzzy matching of a spoken recipient phrase against the customer's saved recipients.

Names are data, never instructions. Ambiguity returns options for the customer to pick, and
a bank word that disagrees with the only name match is treated as ambiguous, not a match.
"""

import re
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Literal

from zolo.ai.nlu.banks import canonical_bank, extract_bank, normalise

TOKEN_MIN = 0.78  # per-word similarity needed to count as the same word
MATCH_MIN = 0.75  # overall score needed to be a candidate
AMBIGUITY_GAP = 0.1  # a runner-up this close to the best is a tie
MAX_OPTIONS = 3  # the PRD allows at most three tappable answers
AMBIGUITY_OPTIONS = 2  # when unsure which saved recipient, offer the top two
PHONETIC_SCORE = 0.8  # same consonants, different vowels ("busy" ~ "Bisi"): sound only
CONCAT_MIN = 0.85  # split or merged words ("chi nedu" ~ "Chinedu")

_FILLER = {
    "my", "the", "our", "one", "from", "at", "for", "to", "on", "in", "with", "inside", "give",
    "abeg", "please", "bank", "account", "naira", "wey", "dey", "na", "am",
}  # fmt: skip


@dataclass(frozen=True)
class SavedRecipient:
    id: str
    display_name: str
    bank: str
    last4: str
    aliases: tuple[str, ...] = ()


@dataclass(frozen=True)
class RecipientMatch:
    recipient: SavedRecipient
    score: float
    strong: bool = True  # False when the match rests on sound alone, never on spelling


@dataclass(frozen=True)
class MatchResult:
    status: Literal["match", "ambiguous", "none"]
    matches: tuple[RecipientMatch, ...] = ()
    bank: str | None = None  # bank key heard in the phrase, if any

    @property
    def recipient(self) -> SavedRecipient | None:
        return self.matches[0].recipient if self.status == "match" else None

    def options(self) -> list[dict[str, str]]:
        """Tappable answers for an `ask` turn."""
        return [
            {"label": f"{m.recipient.display_name}, {m.recipient.bank}", "value": m.recipient.id}
            for m in self.matches[:AMBIGUITY_OPTIONS]
        ]


def _tokens(text: str) -> list[str]:
    return [t for t in normalise(text).split() if t not in _FILLER]


# How a letter sounds when an engine spells a name out: "bc" is "bee see" = "Bisi".
_LETTER_SOUNDS = dict(
    b="bi", c="si", d="di", g="ji", j="je", k="ke", p="pi", t="ti", v="vi", z="zi"
)


def _join_single_letters(tokens: list[str]) -> list[str]:
    """'b c ventures' -> ['bc', 'ventures']: engines often write a name letter by letter."""
    out: list[str] = []
    run = ""
    for t in tokens:
        if len(t) == 1 and t.isalpha():
            run += t
            continue
        if run:
            out.append(run)
            run = ""
        out.append(t)
    if run:
        out.append(run)
    return out


def _spoken_form(token: str) -> tuple[str, bool]:
    """Letter names for a vowel-less token ('bc' -> 'bisi'). Returns (token, was_expanded)."""
    if (
        2 <= len(token) <= 4
        and not set(token) & set("aeiouy")
        and all(c in _LETTER_SOUNDS for c in token)
    ):
        return "".join(_LETTER_SOUNDS[c] for c in token), True
    return token, False


def _skeleton(word: str) -> str:
    """Rough consonant sound of a word, so 'busy', 'Bisi' and 'Bose' share one key ('bs')."""
    w = word.replace("ph", "f").replace("ck", "k").replace("x", "ks").replace("q", "k")
    w = re.sub(r"c(?=[eiy])", "s", w).replace("c", "k").replace("z", "s")
    w = re.sub(r"[aeiouy]", "", w)
    return re.sub(r"(.)\1+", r"\1", w)


def _word_score(q: str, n: str) -> tuple[float, bool]:
    """(score, strong). Strong means spelling supports it, not just sound."""
    if q == n:
        return 1.0, True
    if len(q) <= 3 or len(n) <= 3:
        return 0.0, False  # short words (3 letters or fewer) must match exactly
    r = SequenceMatcher(None, q, n).ratio()
    if r >= TOKEN_MIN:
        return r, True
    sk = _skeleton(q)
    if len(sk) >= 2 and sk == _skeleton(n):
        return PHONETIC_SCORE, False
    return 0.0, False


def _name_score(query: list[tuple[str, bool]], name: list[str]) -> tuple[float, bool]:
    """Score a query (tokens, each flagged 'guessed from letter sounds') against a name."""
    if not query or not name:
        return 0.0, False
    words = [q for q, _ in query]
    if words == name:
        return 1.0, True
    per_word = []
    for q, guessed in query:
        best = max((_word_score(q, n) for n in name), key=lambda s: s[0], default=(0.0, False))
        per_word.append((best[0], best[1] and not guessed))
    score = sum(s for s, _ in per_word) / len(query)
    strong = any(st for _, st in per_word)
    unmatched_name_words = len(name) - min(len(name), sum(1 for s, _ in per_word if s))
    score *= 0.97 if unmatched_name_words else 1.0

    # Split or merged words: compare the query run together with the start of the name.
    joined = "".join(words)
    for k in range(1, len(name) + 1):
        if len(words) < 2 and k < 2:
            continue  # nothing was split or merged: the word-by-word score already covers it
        head = "".join(name[:k])
        r = 1.0 if joined == head else SequenceMatcher(None, joined, head).ratio()
        if r >= CONCAT_MIN and r * (0.97 if k < len(name) else 1.0) > score:
            score, strong = r * (0.97 if k < len(name) else 1.0), True
        elif (
            len(joined) > 3 and len(_skeleton(joined)) >= 2 and _skeleton(joined) == _skeleton(head)
        ):
            if PHONETIC_SCORE * (0.97 if k < len(name) else 1.0) > score:
                score, strong = PHONETIC_SCORE * (0.97 if k < len(name) else 1.0), False
    return score, strong


def _score(recipient: SavedRecipient, query: list[tuple[str, bool]]) -> tuple[float, bool]:
    names = [recipient.display_name, *recipient.aliases]
    return max((_name_score(query, _tokens(n)) for n in names), key=lambda s: s[0])


def find_recipients(phrase: str, saved: list[SavedRecipient]) -> MatchResult:
    bank, rest = extract_bank(normalise(phrase).split())
    tokens = _join_single_letters([t for t in rest if t not in _FILLER])
    query = [_spoken_form(t) for t in tokens]
    if not query:
        return MatchResult("none", bank=bank)

    scored = sorted(
        (
            RecipientMatch(r, score, strong)
            for r in saved
            if (scored_ := _score(r, query))[0] >= MATCH_MIN
            for score, strong in [scored_]
        ),
        key=lambda m: -m.score,
    )
    if not scored:
        return MatchResult("none", bank=bank)

    if bank is not None:
        on_bank = [m for m in scored if canonical_bank(m.recipient.bank) == bank]
        if not on_bank:
            # The name fits but the bank does not: let the customer choose.
            return MatchResult("ambiguous", tuple(scored[:AMBIGUITY_OPTIONS]), bank)
        scored = on_bank

    best = scored[0]
    tied = [m for m in scored if best.score - m.score < AMBIGUITY_GAP]
    if len(tied) > 1:
        return MatchResult("ambiguous", tuple(tied[:AMBIGUITY_OPTIONS]), bank)
    if not best.strong:
        # Sounds like it but is not spelled like it: confirm instead of assuming.
        return MatchResult("ambiguous", tuple(scored[:AMBIGUITY_OPTIONS]), bank)
    return MatchResult("match", (best,), bank)
