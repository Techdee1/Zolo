"""saved_recipients -> the AI package, checked against the real seed data (no database)."""

from zolo.ai.nlu.banks import canonical_bank
from zolo.ai.nlu.recipients import find_recipients
from zolo.bank.codes import BANKS, bank_name
from zolo.demo import seed_data as seed
from zolo.voice.recipients import to_ai_recipient


def test_every_bank_name_is_recognised_by_the_ai_package() -> None:
    # "for Opay" only works by voice if the AI package knows the name we store.
    for code, name in BANKS.items():
        assert canonical_bank(name) is not None, (code, name)


def test_unknown_bank_code_still_has_a_name() -> None:
    assert bank_name("999") == "Bank 999"


def test_a_row_maps_to_an_ai_recipient_with_only_the_last_four_digits() -> None:
    r = to_ai_recipient(seed.RECIPIENTS[2])
    assert (r.display_name, r.bank, r.last4) == ("My sister", "Access Bank", "8901")
    assert r.aliases == ("ADAEZE OKAFOR",)
    assert "0345678901" not in repr(r)  # the full account number never reaches the AI


def _saved():
    return [to_ai_recipient(r) for r in seed.RECIPIENTS]


def test_two_tundes_is_the_disambiguation_case() -> None:
    result = find_recipients("Tunde", _saved())
    assert result.status == "ambiguous"
    assert {o["label"] for o in result.options()} == {"Tunde Bakare, Opay", "Tunde Adeyemi, GTBank"}


def test_a_bank_word_picks_the_right_tunde() -> None:
    assert find_recipients("Tunde for opay", _saved()).recipient.display_name == "Tunde Bakare"  # type: ignore[union-attr]
    assert find_recipients("tunde on gtb", _saved()).recipient.display_name == "Tunde Adeyemi"  # type: ignore[union-attr]


def test_my_sister_and_the_verified_name_both_resolve() -> None:
    assert find_recipients("my sister", _saved()).recipient.display_name == "My sister"  # type: ignore[union-attr]
    assert find_recipients("Adaeze Okafor", _saved()).recipient.display_name == "My sister"  # type: ignore[union-attr]


def test_seed_data_is_internally_consistent() -> None:
    numbers = {(a.account_number, a.bank_code) for a in seed.ACCOUNTS}
    assert len(numbers) == len(seed.ACCOUNTS)  # no duplicate accounts
    for r in seed.RECIPIENTS:  # every saved recipient points at a real seeded account, same name
        match = next(
            a
            for a in seed.ACCOUNTS
            if (a.account_number, a.bank_code) == (r.account_number, r.bank_code)
        )
        assert match.verified_name == r.account_name
    assert seed.WRONG_RECIPIENT_ACCOUNT.verified_name not in {"BISI VENTURES", "MAMA CHI STORES"}
    for a in seed.ACCOUNTS:
        assert not (a.customer_id and a.agent_id)
        assert len(a.account_number) == 10 and a.balance_kobo > 0
