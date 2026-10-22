"""Naira amount parser. Plain, tested code: the LLM never parses money.

parse_amount() returns integer kobo, or None when nothing safe can be read. When in doubt it
returns None or sets confusable, so the caller falls to a keypad check, never a guess.
"""

import re
from dataclasses import dataclass
from fractions import Fraction
from typing import Literal

from zolo.ai.nlu.words import is_confusable_amount
from zolo.ai.nlu.yoruba import parse_yoruba

Confidence = Literal["high", "low"]


@dataclass(frozen=True)
class AmountResult:
    kobo: int | None
    confidence: Confidence
    confusable: bool
    span: tuple[int, int] | None


_NONE = AmountResult(None, "low", False, None)

_UNIT_WORDS = {
    w: i
    for i, w in enumerate(
        ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine"]
    )
} | {"oh": 0}
_TEEN_WORDS = {
    w: 10 + i
    for i, w in enumerate(
        [
            "ten",
            "eleven",
            "twelve",
            "thirteen",
            "fourteen",
            "fifteen",
            "sixteen",
            "seventeen",
            "eighteen",
            "nineteen",
        ]
    )
}
_TENS_WORDS = {
    w: 20 + 10 * i
    for i, w in enumerate(
        ["twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]
    )
}
# scale words -> (rank, multiplier). Rank must strictly fall inside one amount.
_SCALE_WORDS = {
    "thousand": (1, 10**3),
    "k": (1, 10**3),
    "million": (2, 10**6),
    "m": (2, 10**6),
    "billion": (3, 10**9),
}
_SHORT_SCALES = {"k", "m"}  # only count straight after a number
_NUM = re.compile(r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?|[A-Za-z]+")


@dataclass
class _Tok:
    kind: str  # num unit teen tens hundred scale half point and a other
    text: str
    start: int
    end: int
    value: Fraction = Fraction(0)


def _tokenise(text: str) -> list[_Tok]:
    toks: list[_Tok] = []
    for m in _NUM.finditer(text):
        raw, low = m.group(), m.group().lower()
        s, e = m.span()
        if raw[0].isdigit():
            bare = raw.isdigit()
            # Account and phone numbers are not amounts.
            if bare and (len(raw) >= 10 or (raw[0] == "0" and len(raw) > 1)):
                toks.append(_Tok("other", raw, s, e))
            else:
                toks.append(_Tok("num", raw, s, e, Fraction(raw.replace(",", ""))))
        elif low in _UNIT_WORDS:
            toks.append(_Tok("unit", low, s, e, Fraction(_UNIT_WORDS[low])))
        elif low in _TEEN_WORDS:
            toks.append(_Tok("teen", low, s, e, Fraction(_TEEN_WORDS[low])))
        elif low in _TENS_WORDS:
            toks.append(_Tok("tens", low, s, e, Fraction(_TENS_WORDS[low])))
        elif low == "hundred":
            toks.append(_Tok("hundred", low, s, e))
        elif low in _SCALE_WORDS:
            toks.append(_Tok("scale", low, s, e))
        elif low in ("half", "point", "and", "a"):
            toks.append(_Tok(low, low, s, e))
        else:
            toks.append(_Tok("other", low, s, e))
    return toks


_NUMBERISH = {"num", "unit", "teen", "tens", "hundred", "scale", "half", "point"}
_SCALE_LIKE = {"hundred", "scale", "half"}


def _is_single_digit(t: _Tok) -> bool:
    return t.kind == "unit" or (t.kind == "num" and t.text.isdigit() and len(t.text) == 1)


def _runs(toks: list[_Tok]) -> list[list[_Tok]]:
    runs: list[list[_Tok]] = []
    cur: list[_Tok] = []

    def close() -> None:
        nonlocal cur
        if cur:
            runs.append(cur)
        cur = []

    for i, t in enumerate(toks):
        nxt = toks[i + 1] if i + 1 < len(toks) else None
        prev = cur[-1] if cur else None
        if t.kind == "scale" and t.text in _SHORT_SCALES:
            # "15k", "1.5m": only straight after a number, and glued to nothing else.
            if prev is not None and prev.kind in ("num", "unit", "teen", "tens", "hundred", "half"):
                cur.append(t)
            else:
                close()
        elif t.kind in ("num", "unit", "teen", "tens", "hundred", "scale", "half"):
            if (
                t.kind == "num"
                and prev is not None
                and prev.kind == "num"
                and not (_is_single_digit(t) and _is_single_digit(prev))
            ):
                close()
            cur.append(t)
        elif t.kind == "and":
            if cur and nxt is not None and nxt.kind in ("num", "unit", "teen", "tens", "half", "a"):
                cur.append(t)
            else:
                close()
        elif t.kind == "a":
            if nxt is not None and nxt.kind in _SCALE_LIKE and nxt.text not in _SHORT_SCALES:
                if cur and cur[-1].kind not in ("and", "half"):
                    close()
                cur.append(t)
            else:
                close()
        elif t.kind == "point":
            if cur and nxt is not None and _is_single_digit(nxt):
                cur.append(t)
            else:
                close()
        else:
            close()
    close()
    return runs


@dataclass
class _Eval:
    naira: Fraction
    low: bool
    confusable: bool
    strong: bool  # has a scale word, k, or a 3+ digit figure


def _evaluate(run: list[_Tok]) -> _Eval | None:
    toks = [t for t in run if t.kind not in ("and", "a")]
    if not toks:
        return None

    # Digit by digit: "one five zero zero zero".
    if len(toks) >= 2 and all(_is_single_digit(t) for t in toks):
        return _Eval(
            Fraction(int("".join(str(int(t.value)) for t in toks))), len(toks) < 3, False, True
        )

    total, cur = Fraction(0), Fraction(0)
    last: str | None = None
    last_rank = 99
    confusable = False
    strong = False
    has_big_scale = False  # thousand or above seen
    spelled_multiplier = False
    bare_scale = False
    i = 0
    while i < len(toks):
        t = toks[i]
        k = t.kind
        if k == "num":
            if last not in (None, "scale", "hundred"):
                return None
            cur += t.value
            if t.text.isdigit() and len(t.text) >= 3 or "," in t.text:
                strong = True
        elif k == "unit":
            if last not in (None, "tens", "hundred", "scale"):
                return None
            cur += t.value
            spelled_multiplier = True
        elif k in ("teen", "tens"):
            if last not in (None, "hundred", "scale"):
                return None
            cur += t.value
            spelled_multiplier = True
            if 13 <= t.value <= 19 or (30 <= t.value <= 90):
                confusable = True
        elif k == "half":
            if last in ("teen", "tens", "point", "half"):
                return None
            cur += Fraction(1, 2)
            last = "half"
            i += 1
            continue
        elif k == "point":
            if last not in ("num", "unit", "teen", "tens"):
                return None
            digits = ""
            j = i + 1
            while j < len(toks) and _is_single_digit(toks[j]):
                digits += str(int(toks[j].value))
                j += 1
            if not digits:
                return None
            cur += Fraction(int(digits), 10 ** len(digits))
            last = "point"
            i = j
            continue
        elif k == "hundred":
            if last is None:
                bare_scale = True
                cur = Fraction(100)
            elif last in ("unit", "num", "teen", "half") and cur < 100:
                cur *= 100
            else:
                return None
            strong = True
            if not has_big_scale and spelled_multiplier:
                confusable = True  # "five hundred" vs "five k"
        elif k == "scale":
            rank, mult = _SCALE_WORDS[t.text]
            if rank >= last_rank:
                return None
            if last is None:
                bare_scale = True
                total += mult
            elif cur == 0:
                return None
            else:
                total += cur * mult
            cur = Fraction(0)
            last_rank = rank
            strong = True
            has_big_scale = True
            if t.text == "k" and spelled_multiplier:
                confusable = True  # "five k" vs "five hundred"
            spelled_multiplier = False
        last = k if k != "scale" else "scale"
        i += 1
    if last == "half" and total == 0 and cur == Fraction(1, 2):
        return None
    return _Eval(total + cur, bare_scale, confusable, strong)


def _currency_marked(text: str, run: list[_Tok], toks: list[_Tok], idx_after: int) -> bool:
    before = text[: run[0].start].rstrip()
    if before.endswith(("₦", "#")):
        return True
    if before and before[-1] in "nN" and run[0].start - 1 == len(before) - 1:
        if len(before) == 1 or not before[-2].isalpha():
            return True
    after = toks[idx_after] if idx_after < len(toks) else None
    return after is not None and after.text in ("naira", "ngn")


def parse_amount(text: str) -> AmountResult:
    toks = _tokenise(text)
    runs = _runs(toks)
    cands: list[tuple[_Eval, list[_Tok], bool]] = []
    for run in runs:
        idx_after = toks.index(run[-1]) + 1
        after = toks[idx_after] if idx_after < len(toks) else None
        if after is not None and after.text == "kobo":
            return _NONE  # kobo amounts are not supported
        if len(run) >= 10 and all(_is_single_digit(t) for t in run):
            continue  # a spoken account or phone number, not an amount
        ev = _evaluate(run)
        if ev is None:
            return _NONE
        cands.append((ev, run, _currency_marked(text, run, toks, idx_after)))
    if not cands:
        yo = parse_yoruba(text)  # no English number words: try Yoruba (unreviewed, see yoruba.py)
        if yo is None:
            return _NONE
        return AmountResult(
            kobo=yo.naira * 100,
            confidence="low" if yo.bare else "high",
            confusable=is_confusable_amount(yo.naira),
            span=None,
        )

    if len(cands) > 1 and len({c[0].naira for c in cands}) == 1:
        cands = cands[:1]  # the same amount said twice ("15,000 naira, one five zero zero zero")
    if len(cands) > 1:
        strong = [c for c in cands if c[0].strong or c[2]]
        if len(strong) != 1:
            return _NONE  # two plausible amounts: do not pick one
        cands = strong
    ev, run, _ = cands[0]

    if ev.naira.denominator != 1 or ev.naira < 1:
        return _NONE  # below N1, or kobo
    return AmountResult(
        kobo=int(ev.naira) * 100,
        confidence="low" if ev.low else "high",
        # By value, so "15,000", "15k" and "fifteen thousand" are all flagged alike.
        confusable=ev.confusable or is_confusable_amount(int(ev.naira)),
        span=(run[0].start, run[-1].end),
    )
