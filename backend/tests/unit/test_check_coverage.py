import json
from pathlib import Path

import pytest

from zolo.tools.check_coverage import check, main, percent


def report(
    consent: tuple[int, int], passkeys: tuple[int, int], other: tuple[int, int] = (10, 0)
) -> dict[str, object]:
    def entry(covered: int, total: int) -> dict[str, object]:
        return {
            "summary": {
                "covered_lines": covered,
                "num_statements": total,
                "covered_branches": 0,
                "num_branches": 0,
            }
        }

    return {"files": {
        "zolo/consent/service.py": entry(*consent),
        "zolo/passkeys/service.py": entry(*passkeys),
        "zolo/api/routes.py": entry(*other),
    }}  # fmt: skip


def test_a_report_at_or_above_the_minimum_passes() -> None:
    assert check(report((90, 100), (95, 100)), 90) == []  # exactly 90 passes


def test_a_drop_in_either_guarded_package_fails_and_names_it() -> None:
    problems = check(report((89, 100), (95, 100)), 90)
    assert len(problems) == 1 and "zolo/consent/" in problems[0] and "89.0%" in problems[0]
    assert len(check(report((95, 100), (50, 100)), 90)) == 1
    assert len(check(report((10, 100), (10, 100)), 90)) == 2


def test_other_packages_can_be_low_without_failing_the_gate() -> None:
    assert check(report((95, 100), (95, 100), other=(0, 500)), 90) == []


def test_missing_data_is_a_failure_not_a_silent_pass() -> None:
    assert (
        "no coverage data"
        in check(
            {"files": {"zolo/api/x.py": {"summary": {"covered_lines": 1, "num_statements": 1}}}}, 90
        )[0]
    )


def test_branches_count_with_lines() -> None:
    files = {
        "zolo/consent/a.py": {
            "summary": {
                "covered_lines": 10,
                "num_statements": 10,
                "covered_branches": 0,
                "num_branches": 10,
            }
        }
    }
    assert percent(files, "zolo/consent/") == 50.0  # 10 of 20 lines+branches


def test_the_command_exits_nonzero_below_the_minimum(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    good, bad = tmp_path / "good.json", tmp_path / "bad.json"
    good.write_text(json.dumps(report((95, 100), (95, 100))))
    bad.write_text(json.dumps(report((50, 100), (95, 100))))
    assert main([str(good)]) == 0
    assert main([str(bad)]) == 1
    assert "FAIL" in capsys.readouterr().err
