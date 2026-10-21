import pytest

from zolo.ai.nlu.amount import parse_amount
from zolo.ai.nlu.yoruba import parse_yoruba

# Fixed text fixtures only: no Spitch calls. The first row is the transcript Spitch really returned.
FIXTURES = [
    ("ẹgbẹ̀rún mẹ́ẹ̀ẹ́dógún náírà", 15_000),
    ("ẹgbẹ̀rún kan", 1_000),
    ("ẹgbẹ̀rún méjì", 2_000),
    ("ẹgbẹ̀rún mẹ́ta", 3_000),
    ("ẹgbẹ̀rún márùn-ún", 5_000),
    ("ẹgbẹ̀rún mẹ́wàá", 10_000),
    ("ẹgbẹ̀rún mọ́kànlá", 11_000),
    ("ẹgbẹ̀rún ogún", 20_000),
    ("ẹgbẹ̀rún ọgbọ̀n", 30_000),
    ("ẹgbẹ̀rún àádọ́ta", 50_000),
    ("ẹgbẹ̀rún àádọ́rùn-ún", 90_000),
    ("ọgọ́rùn-ún náírà", 100),
    ("igba náírà", 200),
    ("ọ̀ọ́dúnrún", 300),
    ("irinwó", 400),
    ("ẹ̀ẹ́dẹ́gbẹ̀ta", 500),
    ("ẹgbẹ̀ta", 600),
    ("ẹgbẹ̀rin", 800),
    ("ọgọ́rùn-ún márùn-ún", 500),
    ("ọgbọ̀n náírà", 30),
    ("ogún náírà", 20),
    ("ẹgbẹ̀rún mẹ́ta àti igba", 3_200),
    ("ẹgbẹ̀rún mẹ́ẹ̀ẹ́dógún àti ẹ̀ẹ́dẹ́gbẹ̀ta", 15_500),
    ("ẹgbẹ̀rún márùn-ún ó lé irinwó", 5_400),
    ("ogún ó lé márùn-ún", 25),
    ("ọ̀kẹ́ kan", 20_000),
    ("ọ̀kẹ́ márùn-ún", 100_000),
    ("ọ̀kẹ́ mẹ́wàá", 200_000),
    ("ọ̀kẹ́ mẹ́ẹ̀ẹ́dógún", 300_000),
    ("ọ̀kẹ́ ogún", 400_000),
    ("ọ̀kẹ́ mẹ́èédọ́gbọ̀n", 500_000),
    # the same words without tone marks or dots, as some engines write them
    ("egberun meedogun naira", 15_000),
    ("egberun aadota", 50_000),
]


@pytest.mark.parametrize("text,naira", FIXTURES)
def test_common_amounts(text, naira):
    assert parse_yoruba(text).naira == naira
    r = parse_amount(text)
    assert r.kobo == naira * 100 and isinstance(r.kobo, int)


def test_amount_inside_a_sentence():
    heard = "bísí ventures ń bèrè fún ẹgbẹ̀rún mẹ́ẹ̀ẹ́dógún náírà ṣé o fọwọ́ sí i"
    assert parse_amount(heard).kobo == 1_500_000


def test_confusable_by_value_applies_to_yoruba_amounts_too():
    assert parse_amount("ẹgbẹ̀rún mẹ́ẹ̀ẹ́dógún").confusable  # 15,000
    assert parse_amount("ẹgbẹ̀rún àádọ́ta").confusable  # 50,000
    assert not parse_amount("ẹgbẹ̀rún márùn-ún").confusable  # 5,000
    assert not parse_amount("ẹgbẹ̀rún ogún").confusable  # 20,000


def test_bare_scale_word_is_low_confidence():
    r = parse_amount("ẹgbẹ̀rún náírà")
    assert r.kobo == 100_000 and r.confidence == "low"


@pytest.mark.parametrize(
    "text",
    [
        "",
        "bísí ventures ń bèrè fún owó",  # no numerals
        "ẹgbẹ̀rún ẹgbẹ̀rún",  # malformed
        "ọ̀kẹ́ ọgbọ̀n",  # 30 x 20,000 is past 500,000
        "ọ̀kẹ́",  # scale with no count
        "mẹ́ta mẹ́ta",  # two small numerals, no scale
        "ẹgbẹ̀rún márùn-ún ẹgbẹ̀rún mẹ́ta",  # two thousands
        "igba ẹgbẹ̀rún márùn-ún",  # wrong order
        "ẹgbẹ̀rún mẹ́ta ọ̀kẹ́ kan",  # wrong order
        "ẹgbẹ̀rún márùn-ún àti ẹgbẹ̀rún mẹ́ta",
    ],
)
def test_anything_unclear_gives_no_amount(text):
    assert parse_amount(text).kobo is None


def test_stray_kan_is_a_word_not_a_number():
    assert parse_amount("ọkọ̀ kan").kobo is None
    assert parse_amount("owó kan").kobo is None


def test_two_different_amounts_are_not_guessed():
    assert parse_amount("ẹgbẹ̀rún márùn-ún tabi ẹgbẹ̀rún mẹ́jọ").kobo is None


def test_the_same_amount_twice_is_fine():
    assert parse_amount("ẹgbẹ̀rún márùn-ún, ẹgbẹ̀rún márùn-ún").kobo == 500_000


def test_english_still_wins_when_present():
    assert parse_amount("send 5k").kobo == 500_000
