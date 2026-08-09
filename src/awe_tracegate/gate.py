"""Atomic compilation, replay, evaluation, and provenance gating."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timedelta
from typing import Literal

from .compiler import compile_traces, input_bundle_digest
from .contracts import (
    PENDING_SHA256_DIGEST,
    EvaluationBundle,
    EvaluationPolicy,
    EvidencePackage,
    ExecutionTrace,
    GateReceipt,
    GitCommitSha,
    ProvenanceLevel,
    RepositoryUri,
    SkillBom,
    canonical_digest,
)
from .evaluation import evaluate_candidate
from .verifier import verify_compilation_receipt

_PROVENANCE_RANK: dict[ProvenanceLevel, int] = {
    "asserted": 0,
    "signature_verified": 1,
    "attested": 2,
}


def _package_provenance(package: EvidencePackage) -> ProvenanceLevel:
    return min(
        (envelope.provenance_level for envelope in package.envelopes),
        key=_PROVENANCE_RANK.__getitem__,
    )


def gate_receipt_payload(receipt: GateReceipt) -> dict[str, object]:
    """Return the canonical hash payload for an atomic gate receipt."""

    return receipt.model_dump(mode="json", exclude={"receipt_hash"})


def _package_reasons(
    package: EvidencePackage,
    *,
    traces: Sequence[ExecutionTrace],
    baseline: EvaluationBundle,
    candidate: EvaluationBundle,
    policy: EvaluationPolicy,
    expected_repository: RepositoryUri | None,
    expected_commit_sha: GitCommitSha | None,
    evaluated_at: datetime | None,
    maximum_age_seconds: int | None,
    minimum_provenance_level: ProvenanceLevel | None,
    skill_bom: SkillBom | None,
) -> list[str]:
    reasons: list[str] = []
    if (
        expected_repository is not None
        and package.repository_uri != expected_repository
    ):
        reasons.append("evidence_package_repository_mismatch")
    if expected_commit_sha is not None and package.commit_sha != expected_commit_sha:
        reasons.append("evidence_package_commit_mismatch")
    if (
        minimum_provenance_level is not None
        and _PROVENANCE_RANK[_package_provenance(package)]
        < _PROVENANCE_RANK[minimum_provenance_level]
    ):
        reasons.append("evidence_package_provenance_below_minimum")

    expected_payloads = {
        (
            "execution_traces",
            canonical_digest(
                {
                    "traces": [
                        trace.model_dump(mode="json")
                        for trace in sorted(traces, key=lambda item: item.trace_id)
                    ]
                }
            ),
        ),
        ("evaluation_bundle", canonical_digest(baseline)),
        ("evaluation_bundle", canonical_digest(candidate)),
        ("evaluation_policy", canonical_digest(policy)),
    }
    if skill_bom is not None:
        expected_payloads.add(("skill_bom", canonical_digest(skill_bom)))
    available_payloads = {
        (envelope.artifact_kind, envelope.payload_digest)
        for envelope in package.envelopes
    }
    if not expected_payloads.issubset(available_payloads):
        reasons.append("evidence_package_missing_gate_inputs")

    if maximum_age_seconds is not None:
        if evaluated_at is None:
            raise ValueError("maximum evidence age requires an explicit evaluated_at")
        if evaluated_at.utcoffset() != timedelta(0):
            raise ValueError("evaluated_at must include the UTC timezone")
        threshold = timedelta(seconds=maximum_age_seconds)
        timestamps = (
            package.created_at,
            *(envelope.captured_at for envelope in package.envelopes),
        )
        if any(timestamp > evaluated_at for timestamp in timestamps):
            reasons.append("evidence_timestamp_in_future")
        if any(evaluated_at - timestamp > threshold for timestamp in timestamps):
            reasons.append("evidence_package_expired")
    return reasons


def gate_evidence(
    traces: Sequence[ExecutionTrace],
    baseline: EvaluationBundle,
    candidate: EvaluationBundle,
    policy: EvaluationPolicy | None = None,
    *,
    evidence_package: EvidencePackage | None = None,
    expected_repository: RepositoryUri | None = None,
    expected_commit_sha: GitCommitSha | None = None,
    evaluated_at: datetime | None = None,
    maximum_age_seconds: int | None = None,
    minimum_provenance_level: ProvenanceLevel | None = None,
    skill_bom: SkillBom | None = None,
) -> GateReceipt:
    """Create one fail-closed receipt over the complete local evidence chain.

    Inputs are never executed. A PASS requires a compiled read-only candidate,
    exact replay of the supplied traces, a frozen evaluation for that exact
    candidate digest, and (when supplied) a provenance package containing each
    exact gate input.
    """

    if evidence_package is None and any(
        value is not None
        for value in (
            expected_repository,
            expected_commit_sha,
            evaluated_at,
            maximum_age_seconds,
            minimum_provenance_level,
        )
    ):
        raise ValueError("repository, commit, and age checks require evidence package")
    if maximum_age_seconds is not None and maximum_age_seconds < 0:
        raise ValueError("maximum evidence age cannot be negative")
    if maximum_age_seconds is not None and maximum_age_seconds > 31_556_952_000:
        raise ValueError("maximum evidence age exceeds 1,000 years")
    if minimum_provenance_level not in (None, "asserted"):
        raise ValueError(
            "only asserted provenance can be enforced until an external "
            "signature or attestation verifier is configured"
        )

    active_policy = policy or EvaluationPolicy()
    compilation = compile_traces(traces)
    verification = verify_compilation_receipt(compilation, traces)
    evaluation = evaluate_candidate(baseline, candidate, active_policy)

    block_reasons: list[str] = []
    review_reasons: list[str] = []
    if compilation.status != "compiled":
        block_reasons.extend(f"compilation:{reason}" for reason in compilation.reasons)
    if verification.status != "valid":
        block_reasons.extend(
            f"verification:{reason}" for reason in verification.reasons
        )
    if not verification.traces_verified:
        block_reasons.append("verification:exact_trace_replay_required")

    compiled_candidate = compilation.candidate
    candidate_digest = (
        compiled_candidate.candidate_digest if compiled_candidate is not None else None
    )
    if candidate_digest is None:
        block_reasons.append("evaluation:compiled_candidate_unavailable")
    elif candidate.subject_digest != candidate_digest:
        block_reasons.append("evaluation:candidate_digest_mismatch")

    if evaluation.status == "block":
        block_reasons.extend(f"evaluation:{reason}" for reason in evaluation.reasons)
    elif evaluation.status == "review":
        review_reasons.extend(f"evaluation:{reason}" for reason in evaluation.reasons)

    if evidence_package is not None:
        block_reasons.extend(
            _package_reasons(
                evidence_package,
                traces=traces,
                baseline=baseline,
                candidate=candidate,
                policy=active_policy,
                expected_repository=expected_repository,
                expected_commit_sha=expected_commit_sha,
                evaluated_at=evaluated_at,
                maximum_age_seconds=maximum_age_seconds,
                minimum_provenance_level=minimum_provenance_level,
                skill_bom=skill_bom,
            )
        )

    status: Literal["PASS", "REVIEW", "BLOCK", "ERROR"]
    reasons: tuple[str, ...]
    if block_reasons:
        status = "BLOCK"
        reasons = tuple(sorted(set(block_reasons + review_reasons)))
    elif review_reasons:
        status = "REVIEW"
        reasons = tuple(sorted(set(review_reasons)))
    else:
        status = "PASS"
        reasons = ()

    receipt = GateReceipt.model_construct(
        schema_version="awe.gate-receipt.v1",
        gate_version="awe.gate.v1",
        status=status,
        reasons=reasons,
        traces_digest=input_bundle_digest(traces),
        baseline_bundle_digest=canonical_digest(baseline),
        candidate_bundle_digest=canonical_digest(candidate),
        policy_digest=canonical_digest(active_policy),
        skill_bom_digest=(skill_bom.bom_digest if skill_bom is not None else None),
        evidence_package_digest=(
            evidence_package.package_digest if evidence_package is not None else None
        ),
        evidence_provenance_level=(
            _package_provenance(evidence_package)
            if evidence_package is not None
            else None
        ),
        minimum_provenance_level=minimum_provenance_level,
        repository_uri=(
            evidence_package.repository_uri if evidence_package is not None else None
        ),
        commit_sha=(
            evidence_package.commit_sha if evidence_package is not None else None
        ),
        evidence_evaluated_at=evaluated_at,
        maximum_evidence_age_seconds=maximum_age_seconds,
        candidate_digest=candidate_digest,
        compilation=compilation,
        verification=verification,
        evaluation=evaluation,
        receipt_hash=PENDING_SHA256_DIGEST,
    )
    payload = gate_receipt_payload(receipt)
    return GateReceipt.model_validate(
        {**payload, "receipt_hash": canonical_digest(payload)}
    )
