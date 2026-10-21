import pytest

from zolo.ai.nlu.words import digits_spoken, int_to_words, kobo_to_naira_words


@pytest.mark.parametrize(
    "n,words",
    [
        (0, "zero"),
        (5, "five"),
        (13, "thirteen"),
        (30, "thirty"),
        (99, "ninety nine"),
        (100, "one hundred"),
        (2500, "two thousand five hundred"),
        (15000, "fifteen thousand"),
        (15500, "fifteen thousand five hundred"),
        (51000, "fifty one thousand"),
        (500000, "five hundred thousand"),
        (1500000, "one million five hundred thousand"),
        (2_000_000_005, "two billion five"),
    ],
)
def test_int_to_words(n, words):
    assert int_to_words(n) == words


def test_kobo_to_naira_words():
    assert kobo_to_naira_words(1_500_000) == "fifteen thousand"
    with pytest.raises(ValueError):
        kobo_to_naira_words(1_500_050)


def test_out_of_range():
    for bad in (-1, 10**12):
        with pytest.raises(ValueError):
            int_to_words(bad)


@pytest.mark.parametrize(
    "digits,kwargs,spoken",
    [
        (15000, {}, "one five, zero zero zero"),
        (500, {}, "five zero zero"),
        (1500000, {}, "one, five zero zero, zero zero zero"),
        (
            "0123456789",
            {"from_right": False},
            "zero one two, three four five, six seven eight, nine",
        ),
    ],
)
def test_digits_spoken(digits, kwargs, spoken):
    assert digits_spoken(digits, **kwargs) == spoken
