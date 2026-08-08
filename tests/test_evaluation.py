from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from awe_tracegate.contracts import EvaluationBundle, EvaluationTrial
from awe_tracegate.evaluation import evaluate_candidate
from awe_tracegate.promotion import create_promotion_receipt

DATASET = "sha256:" + "a" * 64
BASELINE = "sha256:" + "b" * 64
CANDIDATE = "sha256:" + "c" * 64


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
    blocked = evaluate_candidate(
        bundle(BASELINE),
        bundle(CANDIDATE, safety_violations=1),
    )

    with pytest.raises(ValidationError, match="passing evaluation"):
        create_promotion_receipt(
            blocked,
            decision="approved",
            actor_id="maintainer@example.com",
            commit_sha="a" * 40,
            issued_at=datetime(2026, 8, 8, tzinfo=UTC),
            rationale="Reviewed frozen evaluation evidence.",
        )


def test_records_actor_bound_approval() -> None:
    passed = evaluate_candidate(bundle(BASELINE), bundle(CANDIDATE))

    promotion = create_promotion_receipt(
        passed,
        decision="approved",
        actor_id="maintainer@example.com",
        commit_sha="a" * 40,
        issued_at=datetime(2026, 8, 8, tzinfo=UTC),
        rationale="Reviewed frozen evaluation evidence.",
    )

    assert promotion.decision == "approved"
    assert promotion.evaluation_receipt_hash == passed.receipt_hash
    assert promotion.receipt_hash.startswith("sha256:")
