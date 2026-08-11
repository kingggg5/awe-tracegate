from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).parents[1]
PILOT = ROOT / "examples" / "external_pilot" / "itsdangerous" / "pilot.json"
REPORT = ROOT / "docs" / "validation" / "itsdangerous-compatibility-2026-08-11.md"


def test_public_compatibility_report_matches_machine_readable_evidence() -> None:
    evidence = json.loads(PILOT.read_text(encoding="utf-8"))
    report = REPORT.read_text(encoding="utf-8")

    assert evidence["scope"] == "maintainer_run_compatibility"
    assert evidence["upstream_test_status"] == "passed"
    assert evidence["upstream_tests_passed"] == 297
    assert evidence["commit_sha"] in report
    assert str(evidence["upstream_tests_passed"]) in report
    assert evidence["compilation_receipt_hash"] in report
    assert evidence["verification_hash"] in report
    assert "maintainer-run public compatibility test" in report
    assert "not a third-party" in report
    assert "independent pilot" in report
