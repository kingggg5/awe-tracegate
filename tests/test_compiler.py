from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from awe_tracegate.cli import main
from awe_tracegate.compiler import compile_traces
from awe_tracegate.contracts import ExecutionTrace, canonical_digest

EXAMPLE_TRACES = (
    Path(__file__).parents[1] / "examples" / "repo_analysis" / "traces.jsonl"
)
GOLDEN_RECEIPT = Path(__file__).parent / "golden" / "repo-analysis-receipt.json"


def load_traces() -> tuple[ExecutionTrace, ...]:
    return tuple(
        ExecutionTrace.model_validate_json(line)
        for line in EXAMPLE_TRACES.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )


def validate_trace(payload: dict[str, object]) -> ExecutionTrace:
    return ExecutionTrace.model_validate(payload)


def test_compiles_repeated_read_only_traces_with_proven_dependencies() -> None:
    traces = load_traces()

    receipt = compile_traces(traces)

    assert receipt.status == "compiled"
    assert receipt.reasons == ()
    assert receipt.candidate is not None
    assert receipt.compiler_version == "awe.compiler.v1"
    assert receipt.input_bundle_digest.startswith("sha256:")
    assert receipt.candidate.effect_scope == "pure_or_read"
    assert len(receipt.candidate.nodes) == 3
    assert len(receipt.candidate.dependencies) == 3
    assert receipt.receipt_hash == canonical_digest(
        receipt.model_dump(mode="json", exclude={"receipt_hash"})
    )
    assert all(
        dependency.observation_count == len(traces)
        for dependency in receipt.candidate.dependencies
    )


def test_receipt_is_canonical_when_trace_order_changes() -> None:
    traces = load_traces()

    forward = compile_traces(traces)
    reversed_order = compile_traces(tuple(reversed(traces)))

    assert forward.receipt_hash == reversed_order.receipt_hash
    assert forward.input_bundle_digest == reversed_order.input_bundle_digest
    assert forward.candidate == reversed_order.candidate


def test_receipt_matches_frozen_cross_platform_golden() -> None:
    receipt = compile_traces(load_traces())
    expected = json.loads(GOLDEN_RECEIPT.read_text(encoding="utf-8"))

    assert receipt.model_dump(mode="json", exclude_none=False) == expected


def test_receipt_binds_evidence_not_only_candidate_structure() -> None:
    traces = list(load_traces())
    payload = traces[0].model_dump(mode="python")
    payload["steps"][2]["outputs"][0]["value_digest"] = "sha256:" + "d" * 64
    traces[0] = validate_trace(payload)

    baseline = compile_traces(load_traces())
    changed_evidence = compile_traces(traces)

    assert baseline.candidate == changed_evidence.candidate
    assert baseline.input_bundle_digest != changed_evidence.input_bundle_digest
    assert baseline.receipt_hash != changed_evidence.receipt_hash


def test_trace_contract_is_frozen() -> None:
    trace = load_traces()[0]

    with pytest.raises(ValidationError):
        trace.intent = "changed"  # type: ignore[misc]


def test_single_trace_is_a_cli_refusal_not_a_validation_error(
    tmp_path: Path,
    capsys: object,
) -> None:
    trace_path = tmp_path / "one-trace.jsonl"
    trace_path.write_text(
        load_traces()[0].model_dump_json() + "\n",
        encoding="utf-8",
    )

    exit_code = main(["compile", "--traces", str(trace_path)])
    captured = capsys.readouterr()  # type: ignore[attr-defined]
    body = json.loads(captured.out)

    assert exit_code == 2
    assert body["status"] == "refused"
    assert body["reasons"] == ["insufficient_trace_evidence"]


def test_refuses_write_effects() -> None:
    traces = list(load_traces())
    payload = traces[0].model_dump(mode="python")
    payload["steps"][0]["effect"] = "write"
    traces[0] = validate_trace(payload)

    receipt = compile_traces(traces)

    assert receipt.status == "refused"
    assert receipt.candidate is None
    assert "unsafe_effect:read_diff:write" in receipt.reasons


def test_refuses_ambiguous_value_attribution() -> None:
    traces = list(load_traces())
    payload = traces[0].model_dump(mode="python")
    repeated_digest = payload["steps"][0]["outputs"][0]["value_digest"]
    payload["steps"][0]["outputs"][1]["value_digest"] = repeated_digest
    payload["steps"][2]["inputs"][1]["observed_value_digest"] = repeated_digest
    traces[0] = validate_trace(payload)

    receipt = compile_traces(traces)

    assert receipt.status == "refused"
    assert any(reason.startswith("ambiguous_dependency:") for reason in receipt.reasons)
