from collections import Counter

from zolo.ai.nlu.recipients import find_recipients
from zolo.ai.tools.name_match_report import classify, load


def _counts():
    saved, cases = load()
    return Counter(classify(c, saved) for c in cases), saved, cases


def test_never_a_confident_wrong_recipient_or_a_false_hit():
    counts, _, _ = _counts()
    assert counts["wrong_match"] == 0  # the dangerous case: confidently the wrong person
    assert counts["false_hit"] == 0  # a name we do not have must not match someone
    assert counts["ambiguous_missing"] == 0  # when we ask, the right person is among the options


def test_hit_rates_do_not_regress():
    counts, _, cases = _counts()
    real = [c for c in cases if c["expect"] is not None]
    assert counts["correct"] >= 41  # confident and right
    assert counts["correct"] + counts["correct_ambiguous"] >= len(real) - 1
    assert counts["miss"] <= 1  # known: 'mama she stores'


def test_the_observed_spitch_mangles_of_bisi():
    saved = load()[0]
    for heard in ("bc ventures", "busy ventures", "b c ventures"):
        r = find_recipients(heard, saved)
        assert r.status == "match" and r.recipient.id == "rcp_bisi", heard


def test_a_bare_mangle_asks_between_the_top_two_never_assumes():
    saved = load()[0]
    for heard in ("bc", "busy", "b c"):
        r = find_recipients(heard, saved)
        assert r.status == "ambiguous" and len(r.options()) == 2, heard
        assert "rcp_bisi" in {o["value"] for o in r.options()}


def test_sound_alike_alone_is_never_a_confident_match():
    from zolo.ai.nlu.recipients import SavedRecipient

    only_bisi = [SavedRecipient("r1", "Bisi", "Opay", "1")]
    r = find_recipients("busayo", only_bisi)  # a different name that shares consonants
    assert r.status != "match"


def test_ambiguity_offers_at_most_two_options():
    saved = load()[0]
    assert len(find_recipients("tunde", saved).options()) == 2
