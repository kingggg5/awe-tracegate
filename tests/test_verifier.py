from __future__ import annotations

from pathlib import Path

from awe_tracegate.compiler import compile_traces
from awe_tracegate.contracts import CompilationReceipt, ExecutionTrace
from awe_tracegate.verifier import verify_compilation_receipt

EXAMPLE_TRACES = (
    Path(__file__).parents[1] / "examples" / "repo_analysis" / "traces.jsonl"
)


def load_traces() -> tuple[ExecutionTrace, ...]:
    return tuple(
        ExecutionTrace.model_validate_json(line)
        for line in EXAMPLE_TRACES.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )


def test_verifies_receipt_and_exact_source_traces() -> None:
    traces = load_traces()
    receipt = compile_traces(traces)

    verification = verify_compilation_receipt(receipt, traces)

    assert verification.status == "valid"
    assert verification.traces_verified is True
    assert verification.reasons == ()


def test_detects_tampered_candidate_digest() -> None:
    receipt = compile_traces(load_traces())
    assert receipt.candidate is not None
    tampered_candidate = receipt.candidate.model_copy(
        update={"candidate_digest": "sha256:" + "f" * 64}
    )
    tampered = CompilationReceipt.model_construct(
        **{
            **receipt.model_dump(mode="python"),
            "candidate": tampered_candidate,
        }
    )

    verification = verify_compilation_receipt(tampered)

    assert verification.status == "invalid"
    assert "candidate_digest_mismatch" in verification.reasons
    assert "receipt_hash_mismatch" in verification.reasons


def test_detects_receipt_replayed_against_different_traces() -> None:
    traces = list(load_traces())
    receipt = compile_traces(traces)
    payload = traces[0].model_dump(mode="python")
    payload["steps"][2]["outputs"][0]["value_digest"] = "sha256:" + "e" * 64
    traces[0] = ExecutionTrace.model_validate(payload)

    verification = verify_compilation_receipt(receipt, traces)

    assert verification.status == "invalid"
    assert "input_bundle_digest_mismatch" in verification.reasons
    assert "receipt_replay_mismatch" in verification.reasons
