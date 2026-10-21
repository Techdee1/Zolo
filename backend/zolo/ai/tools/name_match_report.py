"""Score recipient matching on the mangled-transcript set. No network, no credits.

python -m zolo.ai.tools.name_match_report [--verbose]
"""

import argparse
import json
from collections import Counter
from pathlib import Path
from typing import Any

from zolo.ai.nlu.recipients import SavedRecipient, find_recipients

DATA = Path(__file__).resolve().parents[3] / "tests" / "ai" / "data" / "mangled_names.json"


def load() -> tuple[list[SavedRecipient], list[dict[str, Any]]]:
    spec = json.loads(DATA.read_text(encoding="utf-8"))
    saved = [
        SavedRecipient(r["id"], r["name"], r["bank"], "0000", tuple(r.get("aliases", ())))
        for r in spec["recipients"]
    ]
    return saved, spec["cases"]


def classify(case: dict[str, Any], saved: list[SavedRecipient]) -> str:
    """correct, correct_ambiguous, ambiguous_missing, wrong_match, miss, rejected or false_hit."""
    r = find_recipients(case["heard"], saved)
    expect = case["expect"]
    got = [m.recipient.id for m in r.matches]
    if expect is None:
        return "rejected" if r.status == "none" else "false_hit"
    want = {expect} if isinstance(expect, str) else set(expect)
    if r.status == "match":
        return "correct" if got[0] in want and isinstance(expect, str) else "wrong_match"
    if r.status == "ambiguous":
        return "correct_ambiguous" if want & set(got) else "ambiguous_missing"
    return "miss"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    saved, cases = load()
    counts: Counter[str] = Counter()
    for c in cases:
        kind = classify(c, saved)
        counts[kind] += 1
        if args.verbose or kind in ("wrong_match", "false_hit", "miss", "ambiguous_missing"):
            print(f"{kind:18} {c['heard']!r} (expect {c['expect']})")
    positives = sum(v for k, v in counts.items() if k not in ("rejected", "false_hit"))
    print(f"\n{len(cases)} cases ({positives} real names, {len(cases) - positives} not saved)")
    for k in (
        "correct",
        "correct_ambiguous",
        "ambiguous_missing",
        "wrong_match",
        "miss",
        "rejected",
        "false_hit",
    ):
        print(f"  {k:18} {counts[k]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
