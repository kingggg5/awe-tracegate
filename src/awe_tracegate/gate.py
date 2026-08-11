"""Atomic compilation, replay, evaluation, and provenance gating."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal

from .adapters import evaluation_bundle_from_manifest
from .compiler import compile_traces, input_bundle_digest
from .contracts import (
    PENDING_SHA256_DIGEST,
    ComparisonPolicy,
    ComparisonReceipt,
    EvaluationBundle,
    EvaluationPolicy,
    EvidencePackage,
    ExecutionTrace,
    ExperimentManifest,
    ExperimentQualityEvidence,
    ExperimentQualityReceipt,
    GateReceipt,
    GateReceiptV2,
    GitCommitSha,
    ProvenanceLevel,
    QualityPolicy,
    RepositoryUri,
    SkillBom,
    canonical_digest,
)
from .evaluation import (
    evaluate_candidate,
    verify_comparison_receipt_inputs,
)
from .quality import assess_experiment_quality
from .verifier import verify_compilation_receipt

_PROVENANCE_RANK: dict[ProvenanceLevel, int] = {
    "asserted": 0,
    "signature_verified": 1,
    "attested": 2,
}


@dataclass(frozen=True, slots=True)
class GateReplayExpectations:
    """Consumer-owned identity and freshness policy for package replay.

    These values must come from the protected repository or deployment policy,
    never from the untrusted receipt being checked.
    """

    repository_uri: RepositoryUri
    commit_sha: GitCommitSha
    evaluated_at: datetime | None
    maximum_evidence_age_seconds: int | None
    minimum_provenance_level: ProvenanceLevel | None

    def __post_init__(self) -> None:
        if self.evaluated_at is not None and self.evaluated_at.utcoffset() != timedelta(
            0
        ):
            raise ValueError("expected evaluation time must include the UTC timezone")
        if self.maximum_evidence_age_seconds is not None and self.evaluated_at is None:
            raise ValueError("expected maximum evidence age requires evaluated_at")
        if (
            self.maximum_evidence_age_seconds is not None
            and not 0 <= self.maximum_evidence_age_seconds <= 31_556_952_000
        ):
            raise ValueError("expected maximum evidence age is outside policy bounds")
        if self.minimum_provenance_level not in (None, "asserted"):
            raise ValueError(
                "only asserted provenance can be expected until an external "
                "signature or attestation verifier is configured"
            )


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
    exact-input replay of the supplied traces, a frozen evaluation for that exact
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


def validate_gate_receipt_inputs(
    receipt: GateReceipt,
    traces: Sequence[ExecutionTrace],
    baseline: EvaluationBundle,
    candidate: EvaluationBundle,
    policy: EvaluationPolicy | None = None,
    *,
    evidence_package: EvidencePackage | None = None,
    skill_bom: SkillBom | None = None,
    expectations: GateReplayExpectations | None = None,
) -> GateReceipt:
    """Replay a v1 receipt against every exact input it claims to bind.

    Parsing a content-addressed receipt proves internal consistency, not who
    produced it. Consumers that possess the source artifacts must call this
    boundary before trusting the decision. Package-bearing replays also require
    identity and policy expectations obtained independently of the receipt. A
    modified receipt with recomputed hashes cannot weaken those controls.
    """

    if evidence_package is None:
        if expectations is not None:
            raise ValueError("replay expectations require an evidence package")
    elif expectations is None:
        raise ValueError(
            "package replay requires consumer-owned identity and policy expectations"
        )

    if expectations is not None:
        claimed_controls = (
            receipt.evidence_evaluated_at,
            receipt.maximum_evidence_age_seconds,
            receipt.minimum_provenance_level,
        )
        expected_controls = (
            expectations.evaluated_at,
            expectations.maximum_evidence_age_seconds,
            expectations.minimum_provenance_level,
        )
        if claimed_controls != expected_controls:
            raise ValueError("gate receipt does not match consumer-owned controls")

    replayed = gate_evidence(
        traces,
        baseline,
        candidate,
        policy,
        evidence_package=evidence_package,
        expected_repository=(
            expectations.repository_uri if expectations is not None else None
        ),
        expected_commit_sha=(
            expectations.commit_sha if expectations is not None else None
        ),
        evaluated_at=(expectations.evaluated_at if expectations is not None else None),
        maximum_age_seconds=(
            expectations.maximum_evidence_age_seconds
            if expectations is not None
            else None
        ),
        minimum_provenance_level=(
            expectations.minimum_provenance_level if expectations is not None else None
        ),
        skill_bom=skill_bom,
    )
    if replayed.receipt_hash != receipt.receipt_hash:
        raise ValueError("gate receipt does not match exact input replay")
    return receipt


def gate_evidence_v2(
    traces: Sequence[ExecutionTrace],
    baseline: EvaluationBundle,
    candidate: EvaluationBundle,
    evaluation_policy: EvaluationPolicy | None,
    comparison: ComparisonReceipt,
    baseline_manifest: ExperimentManifest,
    candidate_manifest: ExperimentManifest,
    comparison_policy: ComparisonPolicy | None = None,
    *,
    baseline_quality_evidence: ExperimentQualityEvidence | None = None,
    candidate_quality_evidence: ExperimentQualityEvidence | None = None,
    quality_policy: QualityPolicy | None = None,
    evidence_package: EvidencePackage | None = None,
    expected_repository: RepositoryUri | None = None,
    expected_commit_sha: GitCommitSha | None = None,
    evaluated_at: datetime | None = None,
    maximum_age_seconds: int | None = None,
    minimum_provenance_level: ProvenanceLevel | None = None,
    skill_bom: SkillBom | None = None,
) -> GateReceiptV2:
    """Create Gate v2 without changing the existing v1 receipt contract.

    Gate v2 composes the original trace/evaluation decision with a supplied
    ComparisonReceipt that is re-derived from held experiment inputs. Rich
    terminal-state and judge evidence is sidecar data bound to each immutable
    manifest. Nothing in this path runs external tools, models, or graders.
    """

    active_evaluation_policy = evaluation_policy or EvaluationPolicy()
    active_comparison_policy = comparison_policy or ComparisonPolicy()
    active_quality_policy = quality_policy or QualityPolicy()
    v1_gate = gate_evidence(
        traces,
        baseline,
        candidate,
        active_evaluation_policy,
        evidence_package=evidence_package,
        expected_repository=expected_repository,
        expected_commit_sha=expected_commit_sha,
        evaluated_at=evaluated_at,
        maximum_age_seconds=maximum_age_seconds,
        minimum_provenance_level=minimum_provenance_level,
        skill_bom=skill_bom,
    )
    comparison_verification = verify_comparison_receipt_inputs(
        comparison,
        baseline_manifest,
        candidate_manifest,
        active_comparison_policy,
    )
    baseline_quality = (
        assess_experiment_quality(
            baseline_manifest,
            baseline_quality_evidence,
            active_quality_policy,
        )
        if baseline_quality_evidence is not None
        else None
    )
    candidate_quality = (
        assess_experiment_quality(
            candidate_manifest,
            candidate_quality_evidence,
            active_quality_policy,
        )
        if candidate_quality_evidence is not None
        else None
    )

    block_reasons: list[str] = []
    review_reasons: list[str] = []
    if v1_gate.status == "BLOCK":
        block_reasons.extend(f"gate_v1:{reason}" for reason in v1_gate.reasons)
    elif v1_gate.status != "PASS":
        review_reasons.extend(f"gate_v1:{reason}" for reason in v1_gate.reasons)
    if comparison_verification.status != "valid":
        block_reasons.extend(
            f"comparison_verification:{reason}"
            for reason in comparison_verification.reasons
        )
    if comparison.status == "block":
        block_reasons.extend(f"comparison:{reason}" for reason in comparison.reasons)
    elif comparison.status != "pass":
        review_reasons.extend(f"comparison:{reason}" for reason in comparison.reasons)

    expected_baseline_bundle = canonical_digest(
        evaluation_bundle_from_manifest(baseline_manifest)
    )
    expected_candidate_bundle = canonical_digest(
        evaluation_bundle_from_manifest(candidate_manifest)
    )
    if v1_gate.baseline_bundle_digest != expected_baseline_bundle:
        block_reasons.append("comparison_baseline_evaluation_bundle_mismatch")
    if v1_gate.candidate_bundle_digest != expected_candidate_bundle:
        block_reasons.append("comparison_candidate_evaluation_bundle_mismatch")
    if v1_gate.candidate_digest != comparison.candidate_subject_digest:
        block_reasons.append("comparison_candidate_subject_mismatch")

    quality_receipts: tuple[ExperimentQualityReceipt | None, ...] = (
        baseline_quality,
        candidate_quality,
    )
    if any(receipt is None for receipt in quality_receipts):
        review_reasons.append("comparison_quality_evidence_required")
    for label, receipt in (
        ("baseline", baseline_quality),
        ("candidate", candidate_quality),
    ):
        if receipt is None:
            continue
        if receipt.status == "block":
            block_reasons.extend(
                f"{label}_quality:{reason}" for reason in receipt.reasons
            )
        elif receipt.status == "review":
            review_reasons.extend(
                f"{label}_quality:{reason}" for reason in receipt.reasons
            )

    status: Literal["PASS", "REVIEW", "BLOCK", "ERROR"]
    if block_reasons:
        status = "BLOCK"
        reasons = tuple(sorted(set(block_reasons + review_reasons)))
    elif review_reasons:
        status = "REVIEW"
        reasons = tuple(sorted(set(review_reasons)))
    else:
        status = "PASS"
        reasons = ()

    payload = {
        "schema_version": "awe.gate-receipt.v2",
        "gate_version": "awe.gate.v2",
        "status": status,
        "reasons": reasons,
        "v1_gate": v1_gate.model_dump(mode="json"),
        "comparison": comparison.model_dump(mode="json"),
        "comparison_verification": comparison_verification.model_dump(mode="json"),
        "baseline_quality": (
            baseline_quality.model_dump(mode="json")
            if baseline_quality is not None
            else None
        ),
        "candidate_quality": (
            candidate_quality.model_dump(mode="json")
            if candidate_quality is not None
            else None
        ),
    }
    return GateReceiptV2.model_validate(
        {**payload, "receipt_hash": canonical_digest(payload)}
    )


def validate_gate_v2_receipt_inputs(
    receipt: GateReceiptV2,
    traces: Sequence[ExecutionTrace],
    baseline: EvaluationBundle,
    candidate: EvaluationBundle,
    evaluation_policy: EvaluationPolicy | None,
    baseline_manifest: ExperimentManifest,
    candidate_manifest: ExperimentManifest,
    comparison_policy: ComparisonPolicy | None = None,
    *,
    baseline_quality_evidence: ExperimentQualityEvidence | None = None,
    candidate_quality_evidence: ExperimentQualityEvidence | None = None,
    quality_policy: QualityPolicy | None = None,
    evidence_package: EvidencePackage | None = None,
    skill_bom: SkillBom | None = None,
    expectations: GateReplayExpectations | None = None,
) -> GateReceiptV2:
    """Replay Gate v2 against held inputs and independently owned controls."""

    if evidence_package is None:
        if expectations is not None:
            raise ValueError("replay expectations require an evidence package")
    elif expectations is None:
        raise ValueError(
            "package replay requires consumer-owned identity and policy expectations"
        )
    if expectations is not None:
        claimed_controls = (
            receipt.v1_gate.evidence_evaluated_at,
            receipt.v1_gate.maximum_evidence_age_seconds,
            receipt.v1_gate.minimum_provenance_level,
        )
        expected_controls = (
            expectations.evaluated_at,
            expectations.maximum_evidence_age_seconds,
            expectations.minimum_provenance_level,
        )
        if claimed_controls != expected_controls:
            raise ValueError("Gate v2 does not match consumer-owned controls")
    replayed = gate_evidence_v2(
        traces,
        baseline,
        candidate,
        evaluation_policy,
        receipt.comparison,
        baseline_manifest,
        candidate_manifest,
        comparison_policy,
        baseline_quality_evidence=baseline_quality_evidence,
        candidate_quality_evidence=candidate_quality_evidence,
        quality_policy=quality_policy,
        evidence_package=evidence_package,
        expected_repository=(
            expectations.repository_uri if expectations is not None else None
        ),
        expected_commit_sha=(
            expectations.commit_sha if expectations is not None else None
        ),
        evaluated_at=(expectations.evaluated_at if expectations is not None else None),
        maximum_age_seconds=(
            expectations.maximum_evidence_age_seconds
            if expectations is not None
            else None
        ),
        minimum_provenance_level=(
            expectations.minimum_provenance_level if expectations is not None else None
        ),
        skill_bom=skill_bom,
    )
    if replayed.receipt_hash != receipt.receipt_hash:
        raise ValueError("Gate v2 receipt does not match exact input replay")
    return receipt
