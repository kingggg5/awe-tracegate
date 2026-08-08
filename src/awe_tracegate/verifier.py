"""Offline integrity verification for AWE TraceGate receipts."""

from __future__ import annotations

from collections.abc import Sequence

from .compiler import candidate_payload, compile_traces, receipt_payload
from .contracts import (
    CompilationReceipt,
    ExecutionTrace,
    ReceiptVerification,
    canonical_digest,
)


def verify_compilation_receipt(
    receipt: CompilationReceipt,
    traces: Sequence[ExecutionTrace] | None = None,
) -> ReceiptVerification:
    """Recompute receipt internals and, when supplied, its exact source traces."""

    reasons: list[str] = []
    candidate = receipt.candidate
    if candidate is not None:
        expected_candidate_digest = canonical_digest(candidate_payload(candidate))
        if candidate.candidate_digest != expected_candidate_digest:
            reasons.append("candidate_digest_mismatch")

    expected_receipt_hash = canonical_digest(receipt_payload(receipt))
    if receipt.receipt_hash != expected_receipt_hash:
        reasons.append("receipt_hash_mismatch")

    traces_verified = traces is not None
    if traces is not None:
        replayed = compile_traces(traces)
        if replayed.input_bundle_digest != receipt.input_bundle_digest:
            reasons.append("input_bundle_digest_mismatch")
        if replayed.receipt_hash != receipt.receipt_hash:
            reasons.append("receipt_replay_mismatch")

    return ReceiptVerification(
        status="invalid" if reasons else "valid",
        receipt_hash=receipt.receipt_hash,
        traces_verified=traces_verified,
        reasons=tuple(sorted(set(reasons))),
    )
