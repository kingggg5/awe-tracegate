"""Actor-bound human promotion receipts; no action is executed here."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Literal

from .contracts import (
    PENDING_SHA256_DIGEST,
    ActorIdentifier,
    CompilationReceipt,
    EvaluationReceipt,
    ExecutionTrace,
    GitCommitSha,
    PromotionReceipt,
    ReceiptVerification,
    canonical_digest,
)
from .verifier import verify_compilation_receipt


def create_promotion_receipt(
    compilation: CompilationReceipt,
    verification: ReceiptVerification,
    traces: Sequence[ExecutionTrace],
    evaluation: EvaluationReceipt,
    *,
    decision: Literal["approved", "rejected"],
    actor_id: ActorIdentifier,
    commit_sha: GitCommitSha,
    issued_at: datetime,
    rationale: str,
) -> PromotionReceipt:
    """Record a decision only when its full evidence chain is reproducible."""

    if decision not in ("approved", "rejected"):
        raise ValueError("decision must be approved or rejected")

    if compilation.status != "compiled" or compilation.candidate is None:
        raise ValueError("promotion requires a compiled receipt")

    replayed_verification = verify_compilation_receipt(compilation, traces)
    if replayed_verification != verification:
        raise ValueError("verification does not match an exact local replay")
    if replayed_verification.status != "valid":
        raise ValueError("promotion requires a valid verification receipt")
    if not replayed_verification.traces_verified:
        raise ValueError("promotion requires exact trace replay")

    expected_evaluation_hash = canonical_digest(
        evaluation.model_dump(mode="json", exclude={"receipt_hash"})
    )
    if evaluation.receipt_hash != expected_evaluation_hash:
        raise ValueError("evaluation receipt hash is invalid")
    if evaluation.candidate_digest != compilation.candidate.candidate_digest:
        raise ValueError("evaluation candidate digest does not match compilation")

    receipt = PromotionReceipt.model_construct(
        candidate_digest=compilation.candidate.candidate_digest,
        compilation_receipt_hash=compilation.receipt_hash,
        input_bundle_digest=compilation.input_bundle_digest,
        verification_receipt_hash=verification.verification_hash,
        verification_status=verification.status,
        traces_verified=verification.traces_verified,
        evaluation_receipt_hash=evaluation.receipt_hash,
        evaluation_status=evaluation.status,
        dataset_digest=evaluation.dataset_digest,
        policy_digest=evaluation.policy_digest,
        decision=decision,
        actor_id=actor_id,
        commit_sha=commit_sha,
        issued_at=issued_at,
        rationale=rationale,
        receipt_hash=PENDING_SHA256_DIGEST,
    )
    payload = receipt.model_dump(mode="json", exclude={"receipt_hash"})
    return PromotionReceipt.model_validate(
        {**payload, "receipt_hash": canonical_digest(payload)}
    )
