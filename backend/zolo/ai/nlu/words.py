"""Number to words, shared by the parser tests and the readback templates.

English number words only (Phases 1 and 2). Output is space separated with no "and",
which both the parser and TTS read cleanly.
"""

_UNITS = [
    "zero",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
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
_TENS = ["_", "_", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]
_SCALES = ((10**9, "billion"), (10**6, "million"), (10**3, "thousand"))
MAX_WORDS_VALUE = 10**12 - 1


def _below_thousand(n: int) -> list[str]:
    out: list[str] = []
    if n >= 100:
        out += [_UNITS[n // 100], "hundred"]
        n %= 100
    if n >= 20:
        out.append(_TENS[n // 10])
        n %= 10
        if n:
            out.append(_UNITS[n])
    elif n or not out:
        out.append(_UNITS[n])
    return out


def int_to_words(n: int) -> str:
    if not 0 <= n <= MAX_WORDS_VALUE:
        raise ValueError("out of range")
    if n == 0:
        return "zero"
    parts: list[str] = []
    for size, name in _SCALES:
        if n >= size:
            parts += _below_thousand(n // size) + [name]
            n %= size
    if n:
        parts += _below_thousand(n)
    return " ".join(parts)


def kobo_to_naira_words(kobo: int) -> str:
    """Words for the naira amount; the readback template supplies the word 'naira'."""
    if kobo < 0 or kobo % 100:
        raise ValueError("amount must be a whole number of naira")
    return int_to_words(kobo // 100)


def digits_spoken(digits: str | int, group: int = 3, from_right: bool = True) -> str:
    """Read digits one by one in groups: 15000 -> 'one five, zero zero zero'.

    Amounts group from the right; account numbers read better grouped from the left.
    """
    s = str(digits)
    if not s.isdigit():
        raise ValueError("digits only")
    if from_right:
        head = len(s) % group
        chunks = ([s[:head]] if head else []) + [
            s[i : i + group] for i in range(head, len(s), group)
        ]
    else:
        chunks = [s[i : i + group] for i in range(0, len(s), group)]
    return ", ".join(" ".join(_UNITS[int(c)] for c in chunk) for chunk in chunks)


# Teen/ty pairs that sound alike (13/30 ... 19/90). Speech engines swap them, so any amount whose
# English words contain one is "confusable", whether it was said in words or written in digits.
CONFUSABLE_WORDS = frozenset(
    "thirteen fourteen fifteen sixteen seventeen eighteen nineteen "
    "thirty forty fifty sixty seventy eighty ninety".split()
)


def is_confusable_amount(naira: int) -> bool:
    """True if saying this many naira in English uses a teen or a ty word (15,000 and 50,000)."""
    try:
        return not CONFUSABLE_WORDS.isdisjoint(int_to_words(naira).split())
    except ValueError:
        return True  # beyond what we can read back: never trust it


def balance_words(kobo: int) -> str:
    """Words for a balance: whole naira, then kobo if any."""
    naira, rem = divmod(kobo, 100)
    words = int_to_words(naira)
    return f"{words}, {int_to_words(rem)} kobo" if rem else words
