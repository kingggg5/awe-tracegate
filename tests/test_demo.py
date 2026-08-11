from __future__ import annotations

import json
from pathlib import Path

import pytest

from awe_tracegate.cli import main
from awe_tracegate.demo import generate_demo, inspect_review_bundle


def test_demo_generates_a_ready_exact_input_bundle(tmp_path: Path) -> None:
    bundle = tmp_path / "demo"

    generated = generate_demo(bundle)
    report = inspect_review_bundle(bundle)
    replayed_report = inspect_review_bundle(bundle)

    assert len(generated) == 15
    assert report.status == "READY"
    assert report.gate_v2_status == "PASS"
    assert report.gate_v2_receipt_hash is not None
    assert report.explanation_hash is not None
    assert replayed_report == report
    assert tuple(check.check_id for check in report.checks) == (
        "comparison_replay",
        "explanation_replay",
        "gate_replay",
        "typed_contracts",
    )


def test_doctor_fails_closed_for_missing_and_tampered_inputs(tmp_path: Path) -> None:
    incomplete = inspect_review_bundle(tmp_path)
    assert incomplete.status == "INCOMPLETE"
    assert incomplete.checks[0].check_id == "required_files"

    bundle = tmp_path / "demo"
    generate_demo(bundle)
    candidate = json.loads(
        (bundle / "candidate-manifest.json").read_text(encoding="utf-8")
    )
    candidate["model_name"] = "tampered-model"
    (bundle / "candidate-manifest.json").write_text(
        json.dumps(candidate), encoding="utf-8"
    )

    invalid = inspect_review_bundle(bundle)
    assert invalid.status == "INVALID"
    assert invalid.checks[-1].check_id == "replay_integrity"


def test_demo_refuses_to_overwrite_an_existing_directory(tmp_path: Path) -> None:
    output = tmp_path / "demo"
    output.mkdir()
    marker = output / "user-data.txt"
    marker.write_text("preserve me", encoding="utf-8")

    with pytest.raises(ValueError, match="must be empty"):
        generate_demo(output)

    assert marker.read_text(encoding="utf-8") == "preserve me"


def test_cli_demo_and_doctor_have_typed_exit_semantics(tmp_path: Path) -> None:
    output = tmp_path / "demo"
    assert main(["demo", "--out", str(output), "--json"]) == 0
    assert main(["doctor", str(output), "--json"]) == 0
    assert main(["doctor", str(tmp_path / "missing"), "--json"]) == 2
