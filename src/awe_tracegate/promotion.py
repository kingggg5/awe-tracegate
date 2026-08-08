"""Actor-bound human promotion receipts; no action is executed here."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from .contracts import (
    ActorIdentifier,
    EvaluationReceipt,
    GitCommitSha,
    PromotionReceipt,
    canonical_digest,
)


def create_promotion_receipt(
    evaluation: EvaluationReceipt,
    *,
    decision: Literal["approved", "rejected"],
    actor_id: ActorIdentifier,
    commit_sha: GitCommitSha,
    issued_at: datetime,
    rationale: str,
) -> PromotionReceipt:
    """Record a human decision without executing or authorizing side effects."""

    if decision not in ("approved", "rejected"):
        raise ValueError("decision must be approved or rejected")
    expected_evaluation_hash = canonical_digest(
        evaluation.model_dump(mode="json", exclude={"receipt_hash"})
    )
    if evaluation.receipt_hash != expected_evaluation_hash:
        raise ValueError("evaluation receipt hash is invalid")
    receipt = PromotionReceipt(
        candidate_digest=evaluation.candidate_digest,
        evaluation_receipt_hash=evaluation.receipt_hash,
        evaluation_status=evaluation.status,
        decision=decision,
        actor_id=actor_id,
        commit_sha=commit_sha,
        issued_at=issued_at,
        rationale=rationale,
        receipt_hash="sha256:" + "0" * 64,
    )
    payload = receipt.model_dump(mode="json", exclude={"receipt_hash"})
    return receipt.model_copy(update={"receipt_hash": canonical_digest(payload)})
