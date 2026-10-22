import itertools

import pytest

from zolo.ai.types import LANGS
from zolo.consent.machine import ALLOWED, TERMINAL, IllegalTransition, is_allowed
from zolo.consent.readback import build_readback, readback_lang, spoken_name
from zolo.consent.states import LIVE_STATES, State
from zolo.risk.rules import Limits, Verdict, check_daily, check_per_payment, evaluate

# --- the state machine is exactly the PRD table ---

PRD_TABLE = {
    ("CREATED", "READ_BACK"), ("CREATED", "EXPIRED"),
    ("READ_BACK", "APPROVED"), ("READ_BACK", "DECLINED"), ("READ_BACK", "EXPIRED"),
    ("APPROVED", "SUBMITTED"), ("SUBMITTED", "SETTLED"), ("SUBMITTED", "FAILED"),
}  # fmt: skip


def test_allowed_transitions_are_exactly_the_prd_table() -> None:
    assert {(a.value, b.value) for a, b in ALLOWED} == PRD_TABLE


@pytest.mark.parametrize("a,b", list(itertools.product(State, State)))
def test_every_pair_of_states(a: State, b: State) -> None:
    assert is_allowed(a, b) == ((a.value, b.value) in PRD_TABLE)


def test_terminal_states_have_no_exit_and_nothing_goes_backwards() -> None:
    for s in TERMINAL:
        assert not any(is_allowed(s, t) for t in State)
    assert TERMINAL == {State.SETTLED, State.DECLINED, State.EXPIRED, State.FAILED}
    assert not any(is_allowed(b, a) for a, b in ALLOWED)
    assert not any(is_allowed(s, s) for s in State)  # no self-loops


def test_money_can_only_be_reached_through_a_signature() -> None:
    # SUBMITTED (where the transfer is sent) is only reachable from APPROVED, which is only
    # reachable from READ_BACK (the customer heard it).
    assert {a for a, b in ALLOWED if b is State.SUBMITTED} == {State.APPROVED}
    assert {a for a, b in ALLOWED if b is State.APPROVED} == {State.READ_BACK}
    assert LIVE_STATES == (State.CREATED, State.READ_BACK)


def test_illegal_transition_is_a_distinct_programming_error() -> None:
    assert issubclass(IllegalTransition, Exception)


# --- risk rules ---

L = Limits(per_payment_kobo=100_000 * 100, daily_kobo=200_000 * 100)


@pytest.mark.parametrize(
    "amount,ok",
    [(1, True), (100_000 * 100, True), (100_000 * 100 + 1, False), (150_000 * 100, False)],
)
def test_per_payment_cap(amount: int, ok: bool) -> None:
    d = check_per_payment(amount, L)
    assert d.allowed is ok and (ok or (d.verdict is Verdict.BLOCK and d.code == "PER_PAYMENT_CAP"))


@pytest.mark.parametrize(
    "today,amount,ok",
    [(0, 100_000 * 100, True), (100_000 * 100, 100_000 * 100, True),
     (100_000 * 100, 100_000 * 100 + 1, False), (200_000 * 100, 1, False)],
)  # fmt: skip
def test_daily_cap_is_inclusive(today: int, amount: int, ok: bool) -> None:
    d = check_daily(amount, today, L)
    assert d.allowed is ok and (ok or d.code == "DAILY_CAP")


def test_evaluate_reports_the_first_rule_that_fails() -> None:
    assert evaluate(150_000 * 100, 0, L).code == "PER_PAYMENT_CAP"
    assert evaluate(60_000 * 100, 150_000 * 100, L).code == "DAILY_CAP"
    assert evaluate(10_000 * 100, 0, L).allowed


# --- readback text ---


def test_pidgin_readback_matches_the_prd_example() -> None:
    r = build_readback("pcm", "BISI VENTURES", 1_500_000)
    assert r.text == (
        "Bisi Ventures dey ask for fifteen thousand naira. One five, zero zero zero. You wan approve?"
    )
    assert (r.amount_words, r.payee_name) == ("fifteen thousand", "Bisi Ventures")


def test_english_readback() -> None:
    assert build_readback("en", "MAMA CHI STORES", 5_100_000).text == (
        "Mama Chi Stores is asking for fifty one thousand naira. Five one, zero zero zero. Do you approve?"
    )


def test_the_five_languages_have_readbacks_and_nothing_else_does() -> None:
    for lang in LANGS:
        assert readback_lang(lang) == lang
        assert "Bisi Ventures" in build_readback(lang, "BISI VENTURES", 15_000_00).text
    for lang in ("fr", "", "EN", "pt"):
        assert readback_lang(lang) is None
    with pytest.raises(ValueError):
        build_readback("fr", "X", 100_00)  # type: ignore[arg-type]


def test_spoken_name_title_cases_the_banks_capitals() -> None:
    assert spoken_name("BISI VENTURES") == "Bisi Ventures"
    assert spoken_name("O'BRIEN STORES") == "O'Brien Stores"
