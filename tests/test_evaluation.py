from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest
from pydantic import ValidationError

from awe_tracegate.compiler import compile_traces
from awe_tracegate.contracts import EvaluationBundle, EvaluationTrial, ExecutionTrace
from awe_tracegate.evaluation import evaluate_candidate
from awe_tracegate.promotion import create_promotion_receipt
from awe_tracegate.verifier import verify_compilation_receipt

DATASET = "sha256:" + "a" * 64
BASELINE = "sha256:" + "b" * 64
CANDIDATE = "sha256:" + "c" * 64
TRACES_PATH = Path(__file__).parents[1] / "examples" / "repo_analysis" / "traces.jsonl"


def bundle(
    subject: str,
    *,
    successes: tuple[bool, ...] = (True, True, True),
    safety_violations: int = 0,
    latency_ms: int = 100,
    cost_microusd: int = 1_000,
) -> EvaluationBundle:
    return EvaluationBundle(
        subject_digest=subject,
        dataset_digest=DATASET,
        trials=tuple(
            EvaluationTrial(
                trial_id=f"trial_{index}_{subject[-2:]}",
                case_id=f"case_{index}",
                succeeded=succeeded,
                safety_violations=safety_violations,
                latency_ms=latency_ms,
                cost_microusd=cost_microusd,
            )
            for index, succeeded in enumerate(successes, start=1)
        ),
    )


def traces() -> tuple[ExecutionTrace, ...]:
    return tuple(
        ExecutionTrace.model_validate_json(line)
        for line in TRACES_PATH.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )


def promotion_evidence() -> tuple[object, object, tuple[ExecutionTrace, ...], object]:
    source_traces = traces()
    compilation = compile_traces(source_traces)
    assert compilation.candidate is not None
    verification = verify_compilation_receipt(compilation, source_traces)
    evaluation = evaluate_candidate(
        bundle(BASELINE), bundle(compilation.candidate.candidate_digest)
    )
    return compilation, verification, source_traces, evaluation


def test_passes_non_regressing_candidate() -> None:
    receipt = evaluate_candidate(bundle(BASELINE), bundle(CANDIDATE))

    assert receipt.status == "pass"
    assert receipt.reasons == ()
    assert receipt.baseline.success_rate_bps == 10_000


def test_blocks_safety_violation() -> None:
    receipt = evaluate_candidate(
        bundle(BASELINE),
        bundle(CANDIDATE, safety_violations=1),
    )

    assert receipt.status == "block"
    assert "candidate_safety_violation" in receipt.reasons


def test_blocks_dataset_or_case_coverage_mismatch() -> None:
    candidate = bundle(CANDIDATE).model_copy(
        update={"dataset_digest": "sha256:" + "d" * 64}
    )

    receipt = evaluate_candidate(bundle(BASELINE), candidate)

    assert receipt.status == "block"
    assert "dataset_digest_mismatch" in receipt.reasons


def test_human_approval_requires_passing_evaluation() -> None:
    compilation, verification, source_traces, _ = promotion_evidence()
    assert compilation.candidate is not None
    blocked = evaluate_candidate(
        bundle(BASELINE),
        bundle(compilation.candidate.candidate_digest, safety_violations=1),
    )

    with pytest.raises(ValidationError, match="passing evaluation"):
        create_promotion_receipt(
            compilation,
            verification,
            source_traces,
            blocked,
            decision="approved",
            actor_id="maintainer@example.com",
            commit_sha="a" * 40,
            issued_at=datetime(2026, 8, 8, tzinfo=UTC),
            rationale="Reviewed frozen evaluation evidence.",
        )


def test_records_actor_bound_approval() -> None:
    compilation, verification, source_traces, passed = promotion_evidence()

    promotion = create_promotion_receipt(
        compilation,
        verification,
        source_traces,
        passed,
        decision="approved",
        actor_id="maintainer@example.com",
        commit_sha="a" * 40,
        issued_at=datetime(2026, 8, 8, tzinfo=UTC),
        rationale="Reviewed frozen evaluation evidence.",
    )

    assert promotion.decision == "approved"
    assert promotion.candidate_digest == compilation.candidate.candidate_digest
    assert promotion.compilation_receipt_hash == compilation.receipt_hash
    assert promotion.input_bundle_digest == compilation.input_bundle_digest
    assert promotion.verification_receipt_hash == verification.verification_hash
    assert promotion.evaluation_receipt_hash == passed.receipt_hash
    assert promotion.receipt_hash.startswith("sha256:")


def test_promotion_rejects_a_verification_not_reproduced_from_exact_traces() -> None:
    compilation, verification, source_traces, evaluation = promotion_evidence()
    forged_verification = verification.model_copy(update={"traces_verified": False})

    with pytest.raises(ValueError, match="exact local replay"):
        create_promotion_receipt(
            compilation,
            forged_verification,
            source_traces,
            evaluation,
            decision="approved",
            actor_id="maintainer@example.com",
            commit_sha="a" * 40,
            issued_at=datetime(2026, 8, 8, tzinfo=UTC),
            rationale="Replayed source evidence before approval.",
        )


def test_promotion_rejects_an_evaluation_for_another_candidate() -> None:
    compilation, verification, source_traces, _ = promotion_evidence()
    unrelated_evaluation = evaluate_candidate(bundle(BASELINE), bundle(CANDIDATE))

    with pytest.raises(ValueError, match="candidate digest"):
        create_promotion_receipt(
            compilation,
            verification,
            source_traces,
            unrelated_evaluation,
            decision="rejected",
            actor_id="maintainer@example.com",
            commit_sha="a" * 40,
            issued_at=datetime(2026, 8, 8, tzinfo=UTC),
            rationale="Evidence targets a different candidate.",
        )


def test_promotion_receipt_rejects_a_tampered_chain_hash() -> None:
    compilation, verification, source_traces, evaluation = promotion_evidence()
    promotion = create_promotion_receipt(
        compilation,
        verification,
        source_traces,
        evaluation,
        decision="approved",
        actor_id="maintainer@example.com",
        commit_sha="a" * 40,
        issued_at=datetime(2026, 8, 8, tzinfo=UTC),
        rationale="Reviewed a complete replayed evidence chain.",
    )
    tampered = promotion.model_dump(mode="json")
    tampered["receipt_hash"] = "sha256:" + "f" * 64

    with pytest.raises(ValidationError, match="promotion receipt hash"):
        type(promotion).model_validate(tampered)
