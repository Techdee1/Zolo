"""Yoruba number words for common naira amounts (1 to 500,000).

Spitch writes Yoruba amounts in Yoruba words ("ẹgbẹ̀rún mẹ́ẹ̀ẹ́dógún" = 15,000), so the English parser
cannot read them. This covers the forms below and returns None for anything else, so an unknown
phrase still ends in "ask again" and never in a guessed amount.

UNREVIEWED: written from published Yoruba numeral tables, not checked by a native speaker. The
amount still goes through the confusable-by-value rule and the mandatory readback.

Forms handled (tone marks and dots are stripped before matching):
- 1 to 99: counting forms (meji, mẹ́ta ... mẹ́ẹ̀ẹ́dógún ... ogún), tens (ọgbọ̀n, ogójì, àádọ́ta ...).
- hundreds: ọgọ́rùn-ún 100, igba 200, ọ̀ọ́dúnrún 300, irinwó 400, ẹ̀ẹ́dẹ́gbẹ̀ta 500, ẹgbẹ̀ta 600,
  ẹ̀ẹ́dẹ́gbẹ̀rin 700, ẹgbẹ̀rin 800, ẹ̀ẹ́dẹ́gbẹ̀rún 900, or "ọgọ́rùn-ún" with a count (márùn-ún = 500).
- thousands: ẹgbẹ̀rún with a count up to 99 ("ẹgbẹ̀rún mẹ́ta" = 3,000).
- ọ̀kẹ́ (20,000) with a count up to 25 ("ọ̀kẹ́ márùn-ún" = 100,000).
- terms joined by "àti" or "ó lé" (and / more than): "ẹgbẹ̀rún mẹ́ta àti igba" = 3,200.
"""

import re
import unicodedata
from dataclasses import dataclass

MAX_NAIRA = 500_000


def _canon(word: str) -> str:
    """Collapse repeated letters: engines differ on how many vowels a long tone sequence has
    ("mẹ́ẹ̀ẹ́dógún" has three e's), so both the text and our tables are compared in this form."""
    return re.sub(r"(.)\1+", r"\1", word)


def _clauses(text: str) -> list[list[str]]:
    """Tokens per clause; punctuation separates clauses so amounts are not glued together."""
    out: list[list[str]] = []
    for part in re.split(r"[,.;:!?]", text):
        t = unicodedata.normalize("NFKD", part)
        t = "".join(c for c in t if not unicodedata.combining(c))
        t = t.casefold().replace("-", "")  # "ọgọ́rùn-ún" -> "ogorunun"
        words = [_canon(w) for w in re.sub(r"[^a-z]+", " ", t).split()]
        if words:
            out.append(words)
    return out


# Counting forms 1..25 (tone-stripped). "kan" / "okan" are only numbers after a scale word.
_COUNT: dict[str, int] = {}


def _add(value: int, *forms: str) -> None:
    for f in forms:
        _COUNT[_canon(f)] = value


_add(1, "kan", "okan")
_add(2, "meji", "eji")
_add(3, "meta", "eta")
_add(4, "merin", "erin")
_add(5, "marun", "marunun", "aarun", "arun")
_add(6, "mefa", "efa")
_add(7, "meje", "eje")
_add(8, "mejo", "ejo")
_add(9, "mesan", "mesanan", "esan")
_add(10, "mewa", "mewaa", "ewa")
_add(11, "mokanla", "okanla")
_add(12, "mejila", "ejila")
_add(13, "metala")
_add(14, "merinla")
_add(15, "meedogun")
_add(16, "merindinlogun")
_add(17, "metadinlogun")
_add(18, "mejidinlogun")
_add(19, "mokandinlogun")
_add(20, "ogun")
_add(21, "okanlelogun", "mokanlelogun")
_add(22, "mejilelogun")
_add(23, "metalelogun")
_add(24, "merinlelogun")
_add(25, "meedogbon", "eedogbon")

_TENS = {
    _canon(k): v
    for k, v in {
        "ogbon": 30, "ogoji": 40, "aadota": 50, "ogota": 60, "aadorin": 70,
        "aadorun": 90, "aadorunun": 90, "ogorin": 80,
    }.items()
}  # fmt: skip
_HUNDREDS = {
    _canon(k): v
    for k, v in {
        "igba": 200, "oodunrun": 300, "irinwo": 400, "eedegbeta": 500,
        "egbeta": 600, "eedegberin": 700, "egberin": 800, "eedegberun": 900,
    }.items()
}  # fmt: skip
_HUNDRED = {"ogorun", "ogorunun"}
_THOUSAND = {"egberun"}
_OKE = {"oke"}


_BIG = set(_HUNDREDS) | _HUNDRED  # a hundreds word straight after "ẹgbẹ̀rún" is a separate term


@dataclass(frozen=True)
class YorubaAmount:
    naira: int
    bare: bool  # a scale word with no count ("ẹgbẹ̀rún" alone): less certain


def _small(tok: str) -> int | None:
    """1..99 without 'kan': counting forms and tens."""
    if tok in ("kan", "okan"):
        return None
    return _COUNT.get(tok) or _TENS.get(tok)


def _numeral_token(tok: str) -> bool:
    return (
        tok in _COUNT or tok in _TENS or tok in _HUNDREDS or tok in _HUNDRED
        or tok in _THOUSAND or tok in _OKE
    )  # fmt: skip


def _runs(tokens: list[str]) -> list[list[str]]:
    runs: list[list[str]] = []
    cur: list[str] = []
    for i, tok in enumerate(tokens):
        nxt = tokens[i + 1] if i + 1 < len(tokens) else ""
        prev = cur[-1] if cur else ""
        if tok in ("kan", "okan"):
            # a plain word in Yoruba ("a/one"): a number only straight after a scale word
            if prev in _THOUSAND | _OKE | _HUNDRED:
                cur.append(tok)
            else:
                cur = _flush(runs, cur)
        elif _numeral_token(tok):
            cur.append(tok)
        elif tok == "ati" and cur and nxt and _numeral_token(nxt):
            cur.append(tok)
        elif tok == "o" and cur and nxt == "le":
            cur.append("le")
        elif tok == "le" and prev == "le":
            continue
        else:
            cur = _flush(runs, cur)
    _flush(runs, cur)
    return runs


def _flush(runs: list[list[str]], cur: list[str]) -> list[str]:
    if cur:
        runs.append(cur)
    return []


def _evaluate(run: list[str]) -> YorubaAmount | None:
    terms: list[tuple[int, int]] = []  # (class rank, naira)
    bare = False
    i = 0
    toks = list(run)
    while i < len(toks):
        t = toks[i]
        nxt = toks[i + 1] if i + 1 < len(toks) else ""
        if t in ("ati", "le"):
            if not terms or i + 1 >= len(toks):
                return None
            i += 1
            continue
        if t in _THOUSAND:
            n = _small(nxt) if nxt else None
            if nxt in ("kan", "okan"):
                n = 1
            if n is None:
                if nxt and nxt not in ("ati", "le") and _numeral_token(nxt) and nxt not in _BIG:
                    return None
                terms.append((3, 1000))
                bare = True
                i += 1
            else:
                terms.append((3, n * 1000))
                i += 2
        elif t in _OKE:
            n = 1 if nxt in ("kan", "okan") else _COUNT.get(nxt)
            if n is None or n > 25:
                return None
            terms.append((4, n * 20_000))
            i += 2
        elif t in _HUNDRED:
            n = _COUNT.get(nxt) if nxt not in ("kan", "okan", "") else (1 if nxt else None)
            if n is not None and 1 <= n <= 9:
                terms.append((2, n * 100))
                i += 2
            else:
                terms.append((2, 100))
                bare = bare or len(toks) == 1
                i += 1
        elif t in _HUNDREDS:
            terms.append((2, _HUNDREDS[t]))
            i += 1
        else:
            n = _small(t)
            if n is None:
                return None
            terms.append((1, n))
            i += 1

    # Strictly descending classes, except tens + units joined by "ó lé" (ogún ó lé márùn-ún = 25).
    for (ra, va), (rb, vb) in zip(terms, terms[1:], strict=False):
        if rb < ra:
            continue
        if ra == rb == 1 and va % 10 == 0 and vb < 10:
            continue
        return None
    total = sum(v for _, v in terms)
    if not 1 <= total <= MAX_NAIRA:
        return None
    return YorubaAmount(total, bare)


def parse_yoruba(text: str) -> YorubaAmount | None:
    """The one amount in the text, or None (no numerals, malformed, or two different amounts)."""
    values: list[YorubaAmount] = []
    for clause in _clauses(text):
        for run in _runs(clause):
            got = _evaluate(run)
            if got is None:
                return None
            values.append(got)
    if not values or len({v.naira for v in values}) != 1:
        return None
    return values[0]
