"""Money is an integer number of kobo, everywhere. Nothing is silently converted."""

import math

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from zolo.api.schemas import AgentRequestIn, TamperIn

# every JSON value a client could send for an amount
json_values = st.one_of(
    st.integers(min_value=-(10**15), max_value=10**15),
    st.floats(allow_nan=True, allow_infinity=True),
    st.text(max_size=20),
    st.booleans(),
    st.none(),
    st.lists(st.integers(), max_size=2),
    st.dictionaries(st.text(max_size=3), st.integers(), max_size=2),
)


def acceptable(value: object) -> bool:
    return type(value) is int and 0 < value <= 10**12  # a true int (not a bool), in range


@settings(max_examples=500, deadline=None)
@given(json_values)
def test_only_a_true_integer_in_range_is_ever_accepted_as_an_amount(value: object) -> None:
    for model in (AgentRequestIn, TamperIn):
        try:
            parsed = model.model_validate({"amount_kobo": value})
        except ValidationError:
            assert not acceptable(value), f"{value!r} should have been accepted"
        else:
            assert acceptable(value), f"{value!r} was accepted but is not an integer in range"
            assert type(parsed.amount_kobo) is int and parsed.amount_kobo == value


@pytest.mark.parametrize(
    "sneaky",
    [
        "1500000",
        " 1500000 ",
        "1_500_000",
        "1.5e6",
        1500000.0,
        1e6,
        1500000.5,
        True,
        False,
        None,
        [1500000],
    ],
)
def test_values_that_look_like_integers_are_still_refused(sneaky: object) -> None:
    with pytest.raises(ValidationError):
        AgentRequestIn.model_validate({"amount_kobo": sneaky})


def test_floats_that_are_not_numbers_are_refused_too() -> None:
    for bad in (math.nan, math.inf, -math.inf):
        with pytest.raises(ValidationError):
            AgentRequestIn.model_validate({"amount_kobo": bad})


def test_the_boundaries() -> None:
    assert AgentRequestIn.model_validate({"amount_kobo": 1}).amount_kobo == 1
    assert AgentRequestIn.model_validate({"amount_kobo": 10**12}).amount_kobo == 10**12
    for bad in (0, -1, 10**12 + 1):
        with pytest.raises(ValidationError):
            AgentRequestIn.model_validate({"amount_kobo": bad})
