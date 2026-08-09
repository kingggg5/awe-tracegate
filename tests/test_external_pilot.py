from __future__ import annotations

import json
from pathlib import Path

from awe_tracegate.contracts import CompilationReceipt, ExecutionTrace
from awe_tracegate.verifier import verify_compilation_receipt

PILOT_DIRECTORY = (
    Path(__file__).parents[1] / "examples" / "external_pilot" / "itsdangerous"
)


def test_external_itsdangerous_pilot_replays_exact_evidence() -> None:
    traces = tuple(
        ExecutionTrace.model_validate_json(line)
        for line in (PILOT_DIRECTORY / "traces.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    )
    receipt = CompilationReceipt.model_validate_json(
        (PILOT_DIRECTORY / "compilation.json").read_text(encoding="utf-8")
    )
    pilot = json.loads((PILOT_DIRECTORY / "pilot.json").read_text(encoding="utf-8"))

    verification = verify_compilation_receipt(receipt, traces)

    assert pilot["scope"] == "maintainer_run_compatibility"
    assert pilot["commit_sha"] == "672971d66a2ef9f85151e53283113f33d642dabd"
    assert pilot["upstream_tests_passed"] == 297
    assert receipt.receipt_hash == pilot["compilation_receipt_hash"]
    assert verification.status == "valid"
    assert verification.traces_verified is True
    assert verification.verification_hash == pilot["verification_hash"]
