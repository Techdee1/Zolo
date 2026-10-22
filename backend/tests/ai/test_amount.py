import pytest

from zolo.ai.nlu.amount import parse_amount
from zolo.ai.nlu.words import int_to_words

# Every row of the parser table in AI_PRD.md.
TABLE = [
    ("15k", 1_500_000),
    ("15 k", 1_500_000),
    ("fifteen k", 1_500_000),
    ("fifteen thousand naira", 1_500_000),
    ("15,000", 1_500_000),
    ("15000", 1_500_000),
    ("one five zero zero zero", 1_500_000),
    ("two thousand five hundred", 250_000),
    ("1.5m", 150_000_000),
    ("one point five million", 150_000_000),
    ("half a million", 50_000_000),
    ("500k", 50_000_000),
    ("fifteen thousand five hundred", 1_550_000),
    ("fifty", 5_000),
]


@pytest.mark.parametrize("text,kobo", TABLE)
def test_table_rows(text, kobo):
    r = parse_amount(text)
    assert r.kobo == kobo
    assert isinstance(r.kobo, int)


def test_fifty_alone_is_confusable():
    r = parse_amount("fifty")
    assert r.kobo == 5_000 and r.confusable


@pytest.mark.parametrize(
    "text",
    [
        "send 15k to my sister",
        "I want fifteen thousand cash",
        "abeg send 15,000 naira to Tunde for opay",
        "₦15,000",
        "N15,000",
        "send fifteen thousand naira give Mama Chi",
        "twenty-five thousand",
    ],
)
def test_amount_found_inside_sentences(text):
    assert parse_amount(text).kobo is not None


def test_span_points_at_the_amount():
    text = "send 15k to my sister"
    r = parse_amount(text)
    assert r.span is not None and text[r.span[0] : r.span[1]] == "15k"


CONFUSABLE_PAIRS = [
    ("thirteen", "thirty"),
    ("fourteen", "forty"),
    ("fifteen", "fifty"),
    ("sixteen", "sixty"),
    ("seventeen", "seventy"),
    ("eighteen", "eighty"),
    ("nineteen", "ninety"),
]
VALUES = {
    "thirteen": 13, "thirty": 30, "fourteen": 14, "forty": 40, "fifteen": 15, "fifty": 50,
    "sixteen": 16, "sixty": 60, "seventeen": 17, "seventy": 70, "eighteen": 18, "eighty": 80,
    "nineteen": 19, "ninety": 90,
}  # fmt: skip


@pytest.mark.parametrize("teen,ty", CONFUSABLE_PAIRS)
@pytest.mark.parametrize("suffix,mult", [("", 1), (" thousand", 1000), (" k", 1000)])
def test_confusable_pairs_both_sides_flagged(teen, ty, suffix, mult):
    a, b = parse_amount(teen + suffix), parse_amount(ty + suffix)
    assert a.kobo == VALUES[teen] * mult * 100 and a.confusable
    assert b.kobo == VALUES[ty] * mult * 100 and b.confusable


@pytest.mark.parametrize("text", ["twenty", "twelve", "eleven", "ten", "two thousand"])
def test_non_confusable_words_not_flagged(text):
    assert not parse_amount(text).confusable


@pytest.mark.parametrize("text", ["five k", "two k", "five hundred", "five hundred naira"])
def test_k_vs_hundred_flagged(text):
    r = parse_amount(text)
    assert r.kobo is not None and r.confusable


@pytest.mark.parametrize("text", ["5k", "500", "5,000", "two thousand five hundred"])
def test_unambiguous_forms_not_flagged(text):
    assert not parse_amount(text).confusable


def test_k_and_hundred_give_different_amounts():
    assert parse_amount("five k").kobo == 500_000
    assert parse_amount("five hundred").kobo == 50_000


@pytest.mark.parametrize(
    "text",
    [
        "",
        "check my balance",
        "50 kobo",
        "0.50",
        "15.50",
        "0",
        "one point five",  # N1.50
        "half",
        "send 08012345678",  # a phone number is not an amount
        "account 0123456789 amount",
        "five five thousand",  # malformed
        "thousand thousand",
    ],
)
def test_rejected_inputs_give_no_amount(text):
    assert parse_amount(text).kobo is None


def test_two_different_amounts_is_not_guessed():
    assert parse_amount("send 5k or maybe 8k").kobo is None


def test_account_number_does_not_hide_the_amount():
    r = parse_amount("send 15k to 0123456789")
    assert r.kobo == 1_500_000


def test_digit_by_digit_confidence():
    assert parse_amount("one five zero zero zero").confidence == "high"
    assert parse_amount("one five").confidence == "low"


def test_larger_than_scales_still_parse_so_risk_can_cap():
    assert parse_amount("two billion").kobo == 200_000_000_000


def test_round_trip_words_to_amount():
    for n in list(range(1, 3001)) + [9999, 10_000, 15_500, 99_999, 123_456, 1_000_001, 2_500_000]:
        assert parse_amount(int_to_words(n)).kobo == n * 100, n


def test_same_amount_said_twice_is_accepted_but_different_amounts_are_not():
    assert parse_amount("15,000 naira 15000").kobo == 1_500_000
    assert parse_amount("fifteen thousand naira one five zero zero zero").kobo == 1_500_000
    assert parse_amount("5k 8k").kobo is None


def test_unknown_yoruba_words_still_give_no_amount():
    # Common Yoruba amounts parse (see test_yoruba.py); anything we do not know is not guessed.
    assert parse_amount("ẹgbẹ̀rún mẹ́ẹ̀ẹ́dógún náírà").kobo == 1_500_000
    assert parse_amount("ẹgbẹ̀rún ẹgbẹ̀rún náírà").kobo is None


# --- confusable by value: words and digits are flagged alike ---

FORMATS = {
    13: ["thirteen", "13", "thirteen thousand", "13,000", "13000", "13k", "thirteen k"],
    14: ["fourteen", "14", "fourteen thousand", "14,000", "14000", "14k"],
    15: ["fifteen", "15", "fifteen thousand", "15,000", "15000", "15k", "fifteen k"],
    16: ["sixteen", "16", "sixteen thousand", "16,000", "16000", "16k"],
    17: ["seventeen", "17", "seventeen thousand", "17,000", "17000", "17k"],
    18: ["eighteen", "18", "eighteen thousand", "18,000", "18000", "18k"],
    19: ["nineteen", "19", "nineteen thousand", "19,000", "19000", "19k"],
    30: ["thirty", "30", "thirty thousand", "30,000", "30000", "30k", "thirty k"],
    40: ["forty", "40", "forty thousand", "40,000", "40000", "40k"],
    50: ["fifty", "50", "fifty thousand", "50,000", "50000", "50k", "fifty k"],
    60: ["sixty", "60", "sixty thousand", "60,000", "60000", "60k"],
    70: ["seventy", "70", "seventy thousand", "70,000", "70000", "70k"],
    80: ["eighty", "80", "eighty thousand", "80,000", "80000", "80k"],
    90: ["ninety", "90", "ninety thousand", "90,000", "90000", "90k"],
}


@pytest.mark.parametrize("n,text", [(n, t) for n, ts in FORMATS.items() for t in ts])
def test_teen_and_ty_amounts_are_confusable_in_words_and_digits(n, text):
    r = parse_amount(text)
    thousands = any(c in text for c in ("thousand", "000", "k"))
    assert r.kobo == n * (1000 if thousands else 1) * 100
    assert r.confusable, text


def test_15000_versus_50000_both_flagged_and_distinct():
    a, b = parse_amount("15,000"), parse_amount("50,000")
    assert (a.kobo, b.kobo) == (1_500_000, 5_000_000)
    assert a.confusable and b.confusable
    for words, digits in [("fifteen thousand", "15,000"), ("fifty thousand", "50,000")]:
        assert parse_amount(words).kobo == parse_amount(digits).kobo
        assert parse_amount(words).confusable == parse_amount(digits).confusable == True  # noqa: E712


@pytest.mark.parametrize(
    "text",
    ["12,000", "twelve thousand", "20k", "twenty thousand", "25,000", "100,000", "2,500",
     "11k", "10,000", "1.5m", "500", "5k", "7,000", "100", "1,000,000"],
)  # fmt: skip
def test_amounts_without_a_teen_or_ty_are_not_flagged_by_value(text):
    assert not parse_amount(text).confusable


def test_a_teen_or_ty_anywhere_in_the_number_counts():
    assert parse_amount("1,015,000").confusable  # one million fifteen thousand
    assert parse_amount("250,000").confusable  # two hundred fifty thousand
    assert parse_amount("2,500").confusable is False
