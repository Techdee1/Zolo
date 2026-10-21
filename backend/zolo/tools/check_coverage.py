"""Fail the build if coverage of the money-critical packages drops below the PRD's 90%.

    pytest --cov=zolo --cov-report=json:coverage.json
    python -m zolo.tools.check_coverage coverage.json [--min 90]

Lines and branches count together, the same way coverage.py reports a percentage.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Any

GUARDED = ("zolo/consent/", "zolo/passkeys/")


def percent(files: dict[str, Any], prefix: str) -> float | None:
    """Combined line and branch coverage of every file under `prefix`, or None if none ran."""
    statements = covered = 0
    for name, data in files.items():
        if name.replace("\\", "/").startswith(prefix) or f"/{prefix}" in name.replace("\\", "/"):
            s = data["summary"]
            statements += s["num_statements"] + s.get("num_branches", 0)
            covered += s["covered_lines"] + s.get("covered_branches", 0)
    return None if statements == 0 else 100.0 * covered / statements


def check(report: dict[str, Any], minimum: float, guarded: tuple[str, ...] = GUARDED) -> list[str]:
    problems: list[str] = []
    for prefix in guarded:
        got = percent(report["files"], prefix)
        if got is None:
            problems.append(f"{prefix}: no coverage data (were the tests run with --cov=zolo?)")
        elif got < minimum:
            problems.append(f"{prefix}: {got:.1f}% is below the required {minimum:.0f}%")
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("report", type=Path)
    ap.add_argument("--min", type=float, default=90.0)
    args = ap.parse_args(argv)
    report = json.loads(args.report.read_text())
    for prefix in GUARDED:
        got = percent(report["files"], prefix)
        print(f"{prefix:16} {'n/a' if got is None else f'{got:.1f}%'}")
    problems = check(report, args.min)
    for p in problems:
        print(f"FAIL {p}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
