"""Strict, versioned contracts shared by every AWE TraceGate surface."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta
from typing import Annotated, Any, Literal, Self

from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

Identifier = Annotated[
    str,
    StringConstraints(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]*$"),
]
TraceIdentifier = Annotated[
    str,
    StringConstraints(
        min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:-]*$"
    ),
]
ActorIdentifier = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=128,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:@+-]*$",
    ),
]
ToolName = Annotated[
    str,
    StringConstraints(min_length=1, max_length=128, pattern=r"^[a-z][a-z0-9_.-]*$"),
]
ToolVersion = Annotated[
    str,
    StringConstraints(
        min_length=1, max_length=64, pattern=r"^[A-Za-z0-9][A-Za-z0-9.+_-]*$"
    ),
]
JsonPointer = Annotated[
    str,
    StringConstraints(
        min_length=2,
        max_length=256,
        pattern=r"^/(?:[^~\x00-\x1f]|~[01])+$",
    ),
]
Sha256Digest = Annotated[
    str,
    StringConstraints(pattern=r"^sha256:[0-9a-f]{64}$"),
]
# Valid only while constructing an immutable content-addressed model. Callers
# must replace it with the canonical digest before returning the artifact.
PENDING_SHA256_DIGEST: Sha256Digest = "sha256:" + "0" * 64
GitCommitSha = Annotated[
    str,
    StringConstraints(pattern=r"^(?:[0-9a-f]{40}|[0-9a-f]{64})$"),
]
Reason = Annotated[str, StringConstraints(min_length=1, max_length=512)]
DisplayName = Annotated[str, StringConstraints(min_length=1, max_length=256)]
RepositoryUri = Annotated[
    str,
    StringConstraints(
        min_length=12,
        max_length=512,
        pattern=(
            r"^https://[A-Za-z0-9.-]+(?::[0-9]{1,5})?"
            r"/[A-Za-z0-9._~!$&'()*+,;=:@%/-]+$"
        ),
    ),
]
SignerIdentity = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=256,
        pattern=r"^[A-Za-z0-9][A-Za-z0-9._:/@+-]*$",
    ),
]
RelativeArtifactPath = Annotated[
    str,
    StringConstraints(
        min_length=1,
        max_length=512,
        pattern=r"^[^/\\\x00-\x1f][^\\\x00-\x1f]*$",
    ),
]
ExternalUrl = Annotated[
    str,
    StringConstraints(
        min_length=8,
        max_length=2_048,
        pattern=r"^https?://[^\s\x00-\x1f]+$",
    ),
]


def _parse_rfc3339_utc(value: object) -> object:
    """Accept JSON's RFC 3339 timestamp while keeping Python inputs strict."""

    if not isinstance(value, str):
        return value
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return value


UtcDateTime = Annotated[datetime, BeforeValidator(_parse_rfc3339_utc)]

EffectClass = Literal["pure", "read", "write", "high_impact"]
BindingSource = Literal["workflow_input", "step_output", "model_decision"]
DatasetScope = Literal["evaluation", "research", "training"]
RedactionCategory = Literal["secret", "pii", "customer_data", "policy_denied"]
GateStatus = Literal["PASS", "REVIEW", "BLOCK", "ERROR"]
ProvenanceLevel = Literal["asserted", "signature_verified", "attested"]
EvidenceArtifactKind = Literal[
    "execution_traces",
    "evaluation_bundle",
    "evaluation_policy",
    "gate_receipt",
    "skill_bom",
]
TreatmentFactor = Literal["agent_commit", "model", "strategy"]
TerminalOutcome = Literal[
    "success",
    "failure",
    "timeout",
    "refusal",
    "infrastructure_error",
    "missing",
]
JudgeVerdict = Literal["pass", "fail", "abstain"]


class ContractModel(BaseModel):
    """Reject coercion and unknown fields, and prevent attribute mutation."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        validate_default=True,
    )


class FieldEvidence(ContractModel):
    """Content digest observed at a JSON field boundary."""

    field: JsonPointer
    value_digest: Sha256Digest


class TraceBinding(ContractModel):
    """Observed input binding for one executed step."""

    input_name: Identifier
    source_kind: BindingSource
    source_field: JsonPointer
    observed_value_digest: Sha256Digest
    source_node: Identifier | None = None

    @model_validator(mode="after")
    def validate_source_node(self) -> Self:
        if self.source_kind == "step_output" and self.source_node is None:
            raise ValueError("step_output bindings require source_node")
        if self.source_kind != "step_output" and self.source_node is not None:
            raise ValueError("source_node is only valid for step_output bindings")
        return self


class TraceStep(ContractModel):
    """One typed activity observed in an execution trace."""

    node_id: Identifier
    tool: ToolName
    tool_version: ToolVersion
    effect: EffectClass
    inputs: Annotated[
        tuple[TraceBinding, ...],
        Field(max_length=256, strict=False),
    ] = ()
    outputs: Annotated[
        tuple[FieldEvidence, ...],
        Field(min_length=1, max_length=256, strict=False),
    ]

    @model_validator(mode="after")
    def validate_unique_fields(self) -> Self:
        input_names = [binding.input_name for binding in self.inputs]
        if len(input_names) != len(set(input_names)):
            raise ValueError("step input names must be unique")
        output_fields = [evidence.field for evidence in self.outputs]
        if len(output_fields) != len(set(output_fields)):
            raise ValueError("step output fields must be unique")
        return self


class ExecutionTrace(ContractModel):
    """Immutable evidence from a single workflow execution."""

    schema_version: Literal["awe.trace.v1"] = "awe.trace.v1"
    trace_id: TraceIdentifier
    intent: Identifier
    succeeded: bool
    workflow_inputs: Annotated[
        tuple[FieldEvidence, ...],
        Field(min_length=1, max_length=256, strict=False),
    ]
    steps: Annotated[
        tuple[TraceStep, ...],
        Field(min_length=1, max_length=256, strict=False),
    ]

    @model_validator(mode="after")
    def validate_unique_trace_fields(self) -> Self:
        input_fields = [evidence.field for evidence in self.workflow_inputs]
        if len(input_fields) != len(set(input_fields)):
            raise ValueError("workflow input fields must be unique")
        node_ids = [step.node_id for step in self.steps]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("trace node ids must be unique")
        return self


class CompileRequest(ContractModel):
    """Trace set proposed for compilation."""

    traces: Annotated[
        tuple[ExecutionTrace, ...],
        Field(min_length=1, max_length=128, strict=False),
    ]

    @model_validator(mode="after")
    def validate_unique_trace_ids(self) -> Self:
        trace_ids = [trace.trace_id for trace in self.traces]
        if len(trace_ids) != len(set(trace_ids)):
            raise ValueError("trace ids must be unique")
        return self


class CompiledBinding(ContractModel):
    """Binding retained in a declarative compiled candidate."""

    input_name: Identifier
    source_kind: Literal["workflow_input", "step_output"]
    source_field: JsonPointer
    source_node: Identifier | None = None

    @model_validator(mode="after")
    def validate_source_node(self) -> Self:
        if self.source_kind == "step_output" and self.source_node is None:
            raise ValueError("step_output bindings require source_node")
        if self.source_kind == "workflow_input" and self.source_node is not None:
            raise ValueError("workflow_input bindings cannot have source_node")
        return self


class CompiledNode(ContractModel):
    """Read-only node emitted into a candidate workflow."""

    node_id: Identifier
    tool: ToolName
    tool_version: ToolVersion
    effect: Literal["pure", "read"]
    inputs: Annotated[tuple[CompiledBinding, ...], Field(strict=False)] = ()
    output_fields: Annotated[
        tuple[JsonPointer, ...],
        Field(min_length=1, strict=False),
    ]


class DependencyEvidence(ContractModel):
    """Auditable producer-to-consumer dependency observed in every trace."""

    producer_node: Identifier
    producer_field: JsonPointer
    consumer_node: Identifier
    consumer_input: Identifier
    observation_count: Annotated[int, Field(ge=2)]
    trace_ids: Annotated[
        tuple[TraceIdentifier, ...],
        Field(min_length=2, strict=False),
    ]
    evidence_digest: Sha256Digest


class CompilationCandidate(ContractModel):
    """Declarative candidate; it is safe to evaluate, not auto-promote."""

    schema_version: Literal["awe.candidate.v1"] = "awe.candidate.v1"
    candidate_digest: Sha256Digest
    intent: Identifier
    effect_scope: Literal["pure_or_read"] = "pure_or_read"
    source_trace_ids: Annotated[
        tuple[TraceIdentifier, ...],
        Field(min_length=2, strict=False),
    ]
    nodes: Annotated[
        tuple[CompiledNode, ...],
        Field(min_length=1, strict=False),
    ]
    dependencies: Annotated[
        tuple[DependencyEvidence, ...],
        Field(strict=False),
    ] = ()


class CompilationReceipt(ContractModel):
    """Deterministic receipt for either compilation or a safe refusal."""

    schema_version: Literal["awe.compilation-receipt.v1"] = "awe.compilation-receipt.v1"
    compiler_version: Literal["awe.compiler.v1"] = "awe.compiler.v1"
    input_bundle_digest: Sha256Digest
    status: Literal["compiled", "refused"]
    reasons: Annotated[tuple[Reason, ...], Field(strict=False)] = ()
    candidate: CompilationCandidate | None = None
    receipt_hash: Sha256Digest

    @model_validator(mode="after")
    def validate_status_payload(self) -> Self:
        if self.status == "compiled" and self.candidate is None:
            raise ValueError("compiled receipts require a candidate")
        if self.status == "compiled" and self.reasons:
            raise ValueError("compiled receipts cannot contain refusal reasons")
        if self.status == "refused" and self.candidate is not None:
            raise ValueError("refused receipts cannot contain a candidate")
        if self.status == "refused" and not self.reasons:
            raise ValueError("refused receipts require at least one reason")
        return self


class ReceiptVerification(ContractModel):
    """Result of recomputing a compilation receipt and optional source traces."""

    schema_version: Literal["awe.receipt-verification.v2"] = (
        "awe.receipt-verification.v2"
    )
    status: Literal["valid", "invalid"]
    receipt_hash: Sha256Digest
    traces_verified: bool
    reasons: Annotated[tuple[Reason, ...], Field(strict=False)] = ()
    verification_hash: Sha256Digest

    @model_validator(mode="after")
    def validate_status(self) -> Self:
        if self.status == "valid" and self.reasons:
            raise ValueError("valid verification cannot contain reasons")
        if self.status == "invalid" and not self.reasons:
            raise ValueError("invalid verification requires reasons")
        expected_verification_hash = canonical_digest(
            self.model_dump(mode="json", exclude={"verification_hash"})
        )
        if self.verification_hash != expected_verification_hash:
            raise ValueError("verification hash is invalid")
        return self


class EvaluationTrial(ContractModel):
    """One deterministic outcome record from an external evaluation harness."""

    trial_id: TraceIdentifier
    case_id: TraceIdentifier
    succeeded: bool
    safety_violations: Annotated[int, Field(ge=0)] = 0
    latency_ms: Annotated[int, Field(ge=0)]
    cost_microusd: Annotated[int, Field(ge=0)] = 0


class EvaluationBundle(ContractModel):
    """Frozen evaluation results for one exact subject and dataset."""

    schema_version: Literal["awe.evaluation-bundle.v1"] = "awe.evaluation-bundle.v1"
    subject_digest: Sha256Digest
    dataset_digest: Sha256Digest
    trials: Annotated[
        tuple[EvaluationTrial, ...],
        Field(min_length=1, max_length=100_000, strict=False),
    ]

    @model_validator(mode="after")
    def validate_unique_trials(self) -> Self:
        trial_ids = [trial.trial_id for trial in self.trials]
        if len(trial_ids) != len(set(trial_ids)):
            raise ValueError("evaluation trial ids must be unique")
        return self


class EvaluationPolicy(ContractModel):
    """Deterministic non-regression and safety policy."""

    schema_version: Literal["awe.evaluation-policy.v1"] = "awe.evaluation-policy.v1"
    minimum_trials: Annotated[int, Field(ge=1, le=100_000)] = 3
    maximum_success_regression_bps: Annotated[int, Field(ge=0, le=10_000)] = 200
    maximum_latency_increase_bps: Annotated[int, Field(ge=0, le=100_000)] = 2_500
    maximum_cost_increase_bps: Annotated[int, Field(ge=0, le=100_000)] = 2_500
    require_zero_safety_violations: bool = True


class EvaluationMetrics(ContractModel):
    trial_count: Annotated[int, Field(ge=1)]
    success_count: Annotated[int, Field(ge=0)]
    success_rate_bps: Annotated[int, Field(ge=0, le=10_000)]
    safety_violations: Annotated[int, Field(ge=0)]
    p95_latency_ms: Annotated[int, Field(ge=0)]
    total_cost_microusd: Annotated[int, Field(ge=0)]


class EvaluationReceipt(ContractModel):
    """Fail-closed comparison of a baseline and candidate on one frozen dataset."""

    schema_version: Literal["awe.evaluation-receipt.v1"] = "awe.evaluation-receipt.v1"
    evaluator_version: Literal["awe.evaluator.v1"] = "awe.evaluator.v1"
    baseline_digest: Sha256Digest
    candidate_digest: Sha256Digest
    dataset_digest: Sha256Digest
    policy_digest: Sha256Digest
    status: Literal["pass", "review", "block"]
    reasons: Annotated[tuple[Reason, ...], Field(strict=False)] = ()
    baseline: EvaluationMetrics
    candidate: EvaluationMetrics
    receipt_hash: Sha256Digest

    @model_validator(mode="after")
    def validate_status(self) -> Self:
        if self.status == "pass" and self.reasons:
            raise ValueError("passing evaluation cannot contain reasons")
        if self.status != "pass" and not self.reasons:
            raise ValueError("review or block evaluation requires reasons")
        return self


class ComparisonPolicy(ContractModel):
    """Fail-closed policy for a controlled, paired agent comparison."""

    schema_version: Literal["awe.comparison-policy.v1"] = "awe.comparison-policy.v1"
    objective: Literal["improvement", "non_regression"] = "improvement"
    treatment_factors: Annotated[
        tuple[TreatmentFactor, ...], Field(min_length=1, max_length=3, strict=False)
    ] = ("agent_commit",)
    minimum_paired_cases: Annotated[int, Field(ge=2, le=10_000)] = 20
    maximum_supported_paired_cases: Literal[10_000] = 10_000
    minimum_discordant_cases: Annotated[int, Field(ge=1, le=10_000)] = 10
    minimum_repetitions_per_case: Annotated[int, Field(ge=1, le=10_000)] = 2
    minimum_success_improvement_bps: Annotated[int, Field(ge=0, le=10_000)] = 0
    maximum_success_regression_bps: Annotated[int, Field(ge=0, le=10_000)] = 200
    maximum_latency_increase_bps: Annotated[int, Field(ge=0, le=100_000)] = 2_500
    maximum_cost_increase_bps: Annotated[int, Field(ge=0, le=100_000)] = 2_500
    significance_level_bps: Literal[500] = 500
    maximum_confidence_interval_width_bps: Annotated[int, Field(ge=0, le=20_000)] = (
        3_000
    )
    maximum_flaky_case_rate_bps: Annotated[int, Field(ge=0, le=10_000)] = 1_000
    require_zero_safety_violations: bool = True

    @model_validator(mode="after")
    def validate_treatment_factors(self) -> Self:
        if self.treatment_factors != tuple(sorted(set(self.treatment_factors))):
            raise ValueError("treatment factors must be unique and sorted")
        return self


class ComparisonReliability(ContractModel):
    """Reliability evidence scoped to the supplied frozen paired cases."""

    estimand_scope: Literal["frozen_paired_cases"] = "frozen_paired_cases"
    aggregation_method: Literal["paired_case_macro_v1"] = "paired_case_macro_v1"
    paired_trial_count: Annotated[int, Field(ge=1, le=100_000)]
    paired_case_count: Annotated[int, Field(ge=1, le=100_000)]
    repeated_case_count: Annotated[int, Field(ge=0, le=100_000)]
    improved_case_count: Annotated[int, Field(ge=0, le=100_000)]
    regressed_case_count: Annotated[int, Field(ge=0, le=100_000)]
    tied_case_count: Annotated[int, Field(ge=0, le=100_000)]
    discordant_case_count: Annotated[int, Field(ge=0, le=100_000)]
    observed_success_delta_bps: Annotated[int, Field(ge=-10_000, le=10_000)]
    sign_test_method: Literal["exact_two_sided_sign_v1"] = "exact_two_sided_sign_v1"
    sign_test_p_value_ppm: Annotated[int, Field(ge=0, le=1_000_000)]
    confidence_method: Literal["paired_case_normal_95_v1"] = "paired_case_normal_95_v1"
    confidence_level_bps: Literal[9_500] = 9_500
    confidence_interval_lower_bps: Annotated[int, Field(ge=-10_000, le=10_000)]
    confidence_interval_upper_bps: Annotated[int, Field(ge=-10_000, le=10_000)]
    paired_delta_variance_bps_squared: Annotated[int, Field(ge=0, le=200_000_000)]
    baseline_flaky_case_count: Annotated[int, Field(ge=0, le=100_000)]
    candidate_flaky_case_count: Annotated[int, Field(ge=0, le=100_000)]
    flaky_case_count: Annotated[int, Field(ge=0, le=100_000)]
    flaky_case_rate_bps: Annotated[int, Field(ge=0, le=10_000)]
    evidence_strength: Literal["low", "moderate", "high"]

    @model_validator(mode="after")
    def validate_counts_and_interval(self) -> Self:
        if self.repeated_case_count > self.paired_case_count:
            raise ValueError("repeated case count cannot exceed case count")
        if self.baseline_flaky_case_count > self.paired_case_count:
            raise ValueError("baseline flaky case count cannot exceed case count")
        if self.candidate_flaky_case_count > self.paired_case_count:
            raise ValueError("candidate flaky case count cannot exceed case count")
        if self.flaky_case_count > self.paired_case_count:
            raise ValueError("flaky case count cannot exceed case count")
        if (
            self.improved_case_count + self.regressed_case_count + self.tied_case_count
            != self.paired_case_count
        ):
            raise ValueError("case direction counts must cover every paired case")
        if self.discordant_case_count != (
            self.improved_case_count + self.regressed_case_count
        ):
            raise ValueError("discordant case count is inconsistent")
        if self.confidence_interval_lower_bps > self.confidence_interval_upper_bps:
            raise ValueError("confidence interval lower bound exceeds upper bound")
        return self


class ComparisonReceipt(ContractModel):
    """Content-addressed success conclusion for one controlled frozen suite."""

    schema_version: Literal["awe.comparison-receipt.v1"] = "awe.comparison-receipt.v1"
    comparator_version: Literal["awe.comparator.v1"] = "awe.comparator.v1"
    baseline_subject_digest: Sha256Digest
    candidate_subject_digest: Sha256Digest
    baseline_manifest_digest: Sha256Digest
    candidate_manifest_digest: Sha256Digest
    baseline_dataset_digest: Sha256Digest
    candidate_dataset_digest: Sha256Digest
    baseline_dataset_split_digest: Sha256Digest
    candidate_dataset_split_digest: Sha256Digest
    treatment_factors: Annotated[
        tuple[TreatmentFactor, ...], Field(min_length=1, max_length=3, strict=False)
    ]
    treatment_scope: Literal["single_factor", "joint_effect"]
    policy_digest: Sha256Digest
    status: Literal["pass", "review", "block"]
    conclusion: Literal[
        "improvement",
        "non_regression",
        "regression",
        "uncertain",
        "incomparable",
    ]
    reasons: Annotated[tuple[Reason, ...], Field(strict=False)] = ()
    baseline: EvaluationMetrics
    candidate: EvaluationMetrics
    reliability: ComparisonReliability | None
    receipt_hash: Sha256Digest

    @model_validator(mode="after")
    def validate_comparison(self) -> Self:
        if self.treatment_factors != tuple(sorted(set(self.treatment_factors))):
            raise ValueError("comparison treatment factors must be unique and sorted")
        expected_scope = (
            "single_factor" if len(self.treatment_factors) == 1 else "joint_effect"
        )
        if self.treatment_scope != expected_scope:
            raise ValueError("comparison treatment scope is inconsistent")
        if self.status == "pass" and self.reasons:
            raise ValueError("passing comparison cannot contain reasons")
        if self.status != "pass" and not self.reasons:
            raise ValueError("review or block comparison requires reasons")
        if self.status == "pass" and self.reliability is None:
            raise ValueError("passing comparison requires reliability evidence")
        if self.status == "pass" and self.conclusion not in (
            "improvement",
            "non_regression",
        ):
            raise ValueError("passing comparison requires a favorable conclusion")
        if (
            self.status == "pass"
            and self.reliability is not None
            and self.reliability.evidence_strength != "high"
        ):
            raise ValueError("passing comparison requires high-strength evidence")
        if self.conclusion in ("regression", "incomparable") and self.status != "block":
            raise ValueError("regression or incomparable evidence must block")
        if self.conclusion == "incomparable" and self.reliability is not None:
            raise ValueError("incomparable evidence cannot contain paired statistics")
        if self.conclusion != "incomparable" and self.reliability is None:
            raise ValueError("comparable evidence requires paired statistics")
        expected_receipt_hash = canonical_digest(
            self.model_dump(mode="json", exclude={"receipt_hash"})
        )
        if self.receipt_hash != expected_receipt_hash:
            raise ValueError("comparison receipt hash is invalid")
        return self


class ComparisonVerification(ContractModel):
    """Result of replaying one comparison against explicit held inputs.

    A content hash only proves that a receipt is internally self-consistent.
    This record proves whether the receipt was reproduced from the supplied
    baseline, candidate, and policy artifacts without running a model or tool.
    """

    schema_version: Literal["awe.comparison-verification.v1"] = (
        "awe.comparison-verification.v1"
    )
    status: Literal["valid", "invalid"]
    receipt_hash: Sha256Digest
    baseline_manifest_digest: Sha256Digest
    candidate_manifest_digest: Sha256Digest
    policy_digest: Sha256Digest
    reasons: Annotated[tuple[Reason, ...], Field(strict=False)] = ()
    verification_hash: Sha256Digest

    @model_validator(mode="after")
    def validate_verification(self) -> Self:
        if self.status == "valid" and self.reasons:
            raise ValueError("valid comparison verification cannot contain reasons")
        if self.status == "invalid" and not self.reasons:
            raise ValueError("invalid comparison verification requires reasons")
        expected = canonical_digest(
            self.model_dump(mode="json", exclude={"verification_hash"})
        )
        if self.verification_hash != expected:
            raise ValueError("comparison verification hash is invalid")
        return self


class JudgeVote(ContractModel):
    """One asserted grader decision, bound to a versioned grader artifact."""

    judge_id: ActorIdentifier
    judge_digest: Sha256Digest
    verdict: JudgeVerdict


class HumanVerdict(ContractModel):
    """One asserted human adjudication used only for calibration evidence."""

    actor_id: ActorIdentifier
    verdict: JudgeVerdict


class TrialQualityEvidence(ContractModel):
    """Typed terminal outcome and optional adjudication for one frozen trial."""

    trial_id: TraceIdentifier
    terminal_outcome: TerminalOutcome
    judge_votes: Annotated[
        tuple[JudgeVote, ...], Field(max_length=32, strict=False)
    ] = ()
    human_verdict: HumanVerdict | None = None

    @model_validator(mode="after")
    def validate_judges(self) -> Self:
        judge_ids = tuple(vote.judge_id for vote in self.judge_votes)
        if judge_ids != tuple(sorted(set(judge_ids))):
            raise ValueError("judge votes must have unique, sorted judge ids")
        return self


class ExperimentQualityEvidence(ContractModel):
    """Sidecar quality evidence that extends, but never mutates, manifest v1."""

    schema_version: Literal["awe.experiment-quality-evidence.v1"] = (
        "awe.experiment-quality-evidence.v1"
    )
    manifest_digest: Sha256Digest
    trials: Annotated[
        tuple[TrialQualityEvidence, ...],
        Field(min_length=1, max_length=100_000, strict=False),
    ]
    evidence_digest: Sha256Digest

    @model_validator(mode="after")
    def validate_evidence(self) -> Self:
        trial_ids = tuple(trial.trial_id for trial in self.trials)
        if trial_ids != tuple(sorted(set(trial_ids))):
            raise ValueError("quality evidence trial ids must be unique and sorted")
        expected = canonical_digest(
            self.model_dump(mode="json", exclude={"evidence_digest"})
        )
        if self.evidence_digest != expected:
            raise ValueError("experiment quality evidence digest is invalid")
        return self


class QualityPolicy(ContractModel):
    """Fail-closed thresholds for terminal outcomes and judge calibration."""

    schema_version: Literal["awe.quality-policy.v1"] = "awe.quality-policy.v1"
    require_complete_terminal_outcomes: bool = True
    maximum_timeout_rate_bps: Annotated[int, Field(ge=0, le=10_000)] = 0
    maximum_refusal_rate_bps: Annotated[int, Field(ge=0, le=10_000)] = 10_000
    maximum_infrastructure_failure_rate_bps: Annotated[int, Field(ge=0, le=10_000)] = 0
    maximum_missing_trial_rate_bps: Annotated[int, Field(ge=0, le=10_000)] = 0
    minimum_judge_coverage_bps: Annotated[int, Field(ge=0, le=10_000)] = 0
    maximum_judge_disagreement_bps: Annotated[int, Field(ge=0, le=10_000)] = 10_000
    minimum_human_calibration_samples: Annotated[int, Field(ge=0, le=100_000)] = 0
    minimum_human_judge_agreement_bps: Annotated[int, Field(ge=0, le=10_000)] = 0


class TerminalOutcomeSummary(ContractModel):
    """Complete, countable terminal-state distribution for a frozen run."""

    trial_count: Annotated[int, Field(ge=1, le=100_000)]
    success_count: Annotated[int, Field(ge=0)]
    failure_count: Annotated[int, Field(ge=0)]
    timeout_count: Annotated[int, Field(ge=0)]
    refusal_count: Annotated[int, Field(ge=0)]
    infrastructure_failure_count: Annotated[int, Field(ge=0)]
    missing_trial_count: Annotated[int, Field(ge=0)]
    unreported_trial_count: Annotated[int, Field(ge=0)]

    @model_validator(mode="after")
    def validate_total(self) -> Self:
        observed = (
            self.success_count
            + self.failure_count
            + self.timeout_count
            + self.refusal_count
            + self.infrastructure_failure_count
            + self.missing_trial_count
            + self.unreported_trial_count
        )
        if observed != self.trial_count:
            raise ValueError("terminal outcome counts must cover every trial")
        return self


class JudgeCalibration(ContractModel):
    """Coverage and agreement metrics calculated from supplied frozen labels."""

    trial_count: Annotated[int, Field(ge=1, le=100_000)]
    judge_covered_trial_count: Annotated[int, Field(ge=0)]
    multi_judge_trial_count: Annotated[int, Field(ge=0)]
    disagreeing_trial_count: Annotated[int, Field(ge=0)]
    abstaining_vote_count: Annotated[int, Field(ge=0)]
    human_calibration_sample_count: Annotated[int, Field(ge=0)]
    human_judge_agree_count: Annotated[int, Field(ge=0)]
    judge_coverage_bps: Annotated[int, Field(ge=0, le=10_000)]
    judge_disagreement_bps: Annotated[int, Field(ge=0, le=10_000)]
    human_judge_agreement_bps: Annotated[int, Field(ge=0, le=10_000)] | None

    @model_validator(mode="after")
    def validate_counts(self) -> Self:
        if self.judge_covered_trial_count > self.trial_count:
            raise ValueError("judge coverage exceeds trial count")
        if self.multi_judge_trial_count > self.judge_covered_trial_count:
            raise ValueError("multi-judge count exceeds judge coverage")
        if self.disagreeing_trial_count > self.multi_judge_trial_count:
            raise ValueError("judge disagreement exceeds multi-judge count")
        if self.human_judge_agree_count > self.human_calibration_sample_count:
            raise ValueError("human agreement exceeds calibration sample count")
        if (
            self.human_calibration_sample_count == 0
            and self.human_judge_agreement_bps is not None
        ):
            raise ValueError("empty calibration cannot have an agreement rate")
        if (
            self.human_calibration_sample_count > 0
            and self.human_judge_agreement_bps is None
        ):
            raise ValueError("calibration samples require an agreement rate")
        return self


class ExperimentQualityReceipt(ContractModel):
    """Assessment of typed outcomes and grader calibration for one manifest."""

    schema_version: Literal["awe.experiment-quality-receipt.v1"] = (
        "awe.experiment-quality-receipt.v1"
    )
    manifest_digest: Sha256Digest
    quality_evidence_digest: Sha256Digest
    policy_digest: Sha256Digest
    status: Literal["pass", "review", "block"]
    reasons: Annotated[tuple[Reason, ...], Field(strict=False)] = ()
    terminal_outcomes: TerminalOutcomeSummary
    judge_calibration: JudgeCalibration
    receipt_hash: Sha256Digest

    @model_validator(mode="after")
    def validate_receipt(self) -> Self:
        if self.status == "pass" and self.reasons:
            raise ValueError("passing quality receipt cannot contain reasons")
        if self.status != "pass" and not self.reasons:
            raise ValueError("review or block quality receipt requires reasons")
        expected = canonical_digest(
            self.model_dump(mode="json", exclude={"receipt_hash"})
        )
        if self.receipt_hash != expected:
            raise ValueError("experiment quality receipt hash is invalid")
        return self


class GateReceiptV2(ContractModel):
    """Gate v2 composes the immutable v1 decision with a held-input comparison."""

    schema_version: Literal["awe.gate-receipt.v2"] = "awe.gate-receipt.v2"
    gate_version: Literal["awe.gate.v2"] = "awe.gate.v2"
    status: GateStatus
    reasons: Annotated[tuple[Reason, ...], Field(strict=False)] = ()
    v1_gate: GateReceipt
    comparison: ComparisonReceipt
    comparison_verification: ComparisonVerification
    baseline_quality: ExperimentQualityReceipt | None = None
    candidate_quality: ExperimentQualityReceipt | None = None
    receipt_hash: Sha256Digest

    @model_validator(mode="after")
    def validate_chain(self) -> Self:
        if self.status == "PASS" and self.reasons:
            raise ValueError("passing Gate v2 receipt cannot contain reasons")
        if self.status != "PASS" and not self.reasons:
            raise ValueError("non-passing Gate v2 receipt requires reasons")
        if self.comparison_verification.receipt_hash != self.comparison.receipt_hash:
            raise ValueError("Gate v2 verification does not bind comparison receipt")
        if self.v1_gate.candidate_digest != self.comparison.candidate_subject_digest:
            raise ValueError("Gate v2 candidate does not bind comparison subject")
        if self.baseline_quality is not None and (
            self.baseline_quality.manifest_digest
            != self.comparison.baseline_manifest_digest
        ):
            raise ValueError("Gate v2 baseline quality targets another manifest")
        if self.candidate_quality is not None and (
            self.candidate_quality.manifest_digest
            != self.comparison.candidate_manifest_digest
        ):
            raise ValueError("Gate v2 candidate quality targets another manifest")
        if self.status == "PASS":
            if self.v1_gate.status != "PASS":
                raise ValueError("passing Gate v2 requires passing Gate v1")
            if self.comparison.status != "pass":
                raise ValueError("passing Gate v2 requires passing comparison")
            if self.comparison_verification.status != "valid":
                raise ValueError(
                    "passing Gate v2 requires held-input comparison replay"
                )
            if (
                self.candidate_quality is None
                or self.candidate_quality.status != "pass"
            ):
                raise ValueError("passing Gate v2 requires candidate quality evidence")
        expected = canonical_digest(
            self.model_dump(mode="json", exclude={"receipt_hash"})
        )
        if self.receipt_hash != expected:
            raise ValueError("Gate v2 receipt hash is invalid")
        return self


class SensitivityPolicy(ContractModel):
    """Bounded checks for environment and seed sensitivity in frozen runs."""

    schema_version: Literal["awe.sensitivity-policy.v1"] = "awe.sensitivity-policy.v1"
    minimum_environment_count: Annotated[int, Field(ge=2, le=100)] = 2
    minimum_seed_count: Annotated[int, Field(ge=2, le=10_000)] = 2
    maximum_environment_success_range_bps: Annotated[int, Field(ge=0, le=10_000)] = (
        1_000
    )
    maximum_seed_success_range_bps: Annotated[int, Field(ge=0, le=10_000)] = 1_000


class SensitivityReceipt(ContractModel):
    """Deterministic stability assessment across frozen environments and seeds."""

    schema_version: Literal["awe.sensitivity-receipt.v1"] = "awe.sensitivity-receipt.v1"
    subject_digest: Sha256Digest
    dataset_digest: Sha256Digest
    dataset_split_digest: Sha256Digest
    manifest_digests: Annotated[
        tuple[Sha256Digest, ...], Field(min_length=2, max_length=100, strict=False)
    ]
    environment_digests: Annotated[
        tuple[Sha256Digest, ...], Field(min_length=1, max_length=100, strict=False)
    ]
    policy_digest: Sha256Digest
    status: Literal["pass", "review", "block"]
    reasons: Annotated[tuple[Reason, ...], Field(strict=False)] = ()
    environment_success_range_bps: Annotated[int, Field(ge=0, le=10_000)] | None
    seed_success_range_bps: Annotated[int, Field(ge=0, le=10_000)] | None
    receipt_hash: Sha256Digest

    @model_validator(mode="after")
    def validate_receipt(self) -> Self:
        if self.manifest_digests != tuple(sorted(set(self.manifest_digests))):
            raise ValueError("sensitivity manifest digests must be unique and sorted")
        if self.environment_digests != tuple(sorted(set(self.environment_digests))):
            raise ValueError(
                "sensitivity environment digests must be unique and sorted"
            )
        if self.status == "pass" and self.reasons:
            raise ValueError("passing sensitivity receipt cannot contain reasons")
        if self.status != "pass" and not self.reasons:
            raise ValueError("review or block sensitivity receipt requires reasons")
        expected = canonical_digest(
            self.model_dump(mode="json", exclude={"receipt_hash"})
        )
        if self.receipt_hash != expected:
            raise ValueError("sensitivity receipt hash is invalid")
        return self


class EvidenceGraphNode(ContractModel):
    """A compact, content-addressed node in an explainable receipt graph."""

    node_id: TraceIdentifier
    kind: ToolName
    digest: Sha256Digest
    status: DisplayName


class EvidenceGraphEdge(ContractModel):
    """A directed dependency edge; its endpoints are local graph node IDs."""

    source: TraceIdentifier
    target: TraceIdentifier
    relation: Literal["derived_from", "verified_by", "assessed_by", "gated_by"]


class ExplanationReceipt(ContractModel):
    """Offline explanation graph for a parsed AWE receipt; it is not an LLM summary."""

    schema_version: Literal["awe.explanation-receipt.v1"] = "awe.explanation-receipt.v1"
    receipt_schema_version: DisplayName
    receipt_hash: Sha256Digest
    decision: DisplayName
    reasons: Annotated[tuple[Reason, ...], Field(strict=False)] = ()
    nodes: Annotated[
        tuple[EvidenceGraphNode, ...], Field(min_length=1, max_length=128, strict=False)
    ]
    edges: Annotated[tuple[EvidenceGraphEdge, ...], Field(max_length=256, strict=False)]
    limitations: Annotated[tuple[Reason, ...], Field(min_length=1, strict=False)]
    explanation_hash: Sha256Digest

    @model_validator(mode="after")
    def validate_graph(self) -> Self:
        node_ids = tuple(node.node_id for node in self.nodes)
        if node_ids != tuple(sorted(set(node_ids))):
            raise ValueError("explanation graph node ids must be unique and sorted")
        if self.edges != tuple(
            sorted(
                self.edges, key=lambda edge: (edge.source, edge.target, edge.relation)
            )
        ):
            raise ValueError("explanation graph edges must be sorted")
        if any(
            edge.source not in node_ids or edge.target not in node_ids
            for edge in self.edges
        ):
            raise ValueError("explanation edge refers to an unknown node")
        expected = canonical_digest(
            self.model_dump(mode="json", exclude={"explanation_hash"})
        )
        if self.explanation_hash != expected:
            raise ValueError("explanation receipt hash is invalid")
        return self


class GateReceipt(ContractModel):
    """Atomic, content-addressed decision over one complete evidence chain."""

    schema_version: Literal["awe.gate-receipt.v1"] = "awe.gate-receipt.v1"
    gate_version: Literal["awe.gate.v1"] = "awe.gate.v1"
    status: GateStatus
    reasons: Annotated[tuple[Reason, ...], Field(strict=False)] = ()
    traces_digest: Sha256Digest
    baseline_bundle_digest: Sha256Digest
    candidate_bundle_digest: Sha256Digest
    policy_digest: Sha256Digest
    skill_bom_digest: Sha256Digest | None = None
    evidence_package_digest: Sha256Digest | None = None
    evidence_provenance_level: ProvenanceLevel | None = None
    minimum_provenance_level: ProvenanceLevel | None = None
    repository_uri: RepositoryUri | None = None
    commit_sha: GitCommitSha | None = None
    evidence_evaluated_at: UtcDateTime | None = None
    maximum_evidence_age_seconds: (
        Annotated[int, Field(ge=0, le=31_556_952_000)] | None
    ) = None
    candidate_digest: Sha256Digest | None = None
    compilation: CompilationReceipt
    verification: ReceiptVerification
    evaluation: EvaluationReceipt
    receipt_hash: Sha256Digest

    @model_validator(mode="after")
    def validate_chain(self) -> Self:
        if self.status == "PASS" and self.reasons:
            raise ValueError("passing gate receipt cannot contain reasons")
        if self.status != "PASS" and not self.reasons:
            raise ValueError("non-passing gate receipt requires reasons")
        if self.compilation.input_bundle_digest != self.traces_digest:
            raise ValueError("gate traces digest does not match compilation")
        provenance_values = (
            self.evidence_package_digest,
            self.evidence_provenance_level,
            self.repository_uri,
            self.commit_sha,
        )
        if any(value is not None for value in provenance_values) and not all(
            value is not None for value in provenance_values
        ):
            raise ValueError("gate package provenance must be complete")
        if self.maximum_evidence_age_seconds is not None:
            if self.evidence_package_digest is None:
                raise ValueError("evidence age policy requires a package")
            if self.evidence_evaluated_at is None:
                raise ValueError("evidence age policy requires evaluation time")
        if (
            self.minimum_provenance_level is not None
            and self.evidence_package_digest is None
        ):
            raise ValueError("minimum provenance policy requires a package")
        if self.minimum_provenance_level is not None:
            provenance_rank = {
                "asserted": 0,
                "signature_verified": 1,
                "attested": 2,
            }
            if self.evidence_provenance_level is None:
                raise ValueError("gate package provenance level is missing")
            below_minimum = (
                provenance_rank[self.evidence_provenance_level]
                < provenance_rank[self.minimum_provenance_level]
            )
            if below_minimum and not (
                self.status == "BLOCK"
                and "evidence_package_provenance_below_minimum" in self.reasons
            ):
                raise ValueError("gate package provenance is below policy")
        if (
            self.evidence_evaluated_at is not None
            and self.evidence_evaluated_at.utcoffset() != timedelta(0)
        ):
            raise ValueError("evidence evaluation time must include the UTC timezone")
        expected_compilation_hash = canonical_digest(
            self.compilation.model_dump(mode="json", exclude={"receipt_hash"})
        )
        if self.compilation.receipt_hash != expected_compilation_hash:
            raise ValueError("gate compilation receipt hash is invalid")
        if self.verification.receipt_hash != self.compilation.receipt_hash:
            raise ValueError("gate verification does not bind the compilation")
        expected_evaluation_hash = canonical_digest(
            self.evaluation.model_dump(mode="json", exclude={"receipt_hash"})
        )
        if self.evaluation.receipt_hash != expected_evaluation_hash:
            raise ValueError("gate evaluation receipt hash is invalid")
        if self.evaluation.policy_digest != self.policy_digest:
            raise ValueError("gate policy digest does not match evaluation")
        compiled_candidate = self.compilation.candidate
        if compiled_candidate is None:
            if self.candidate_digest is not None:
                raise ValueError("refused compilation cannot bind a candidate")
        else:
            expected_candidate_digest = canonical_digest(
                compiled_candidate.model_dump(mode="json", exclude={"candidate_digest"})
            )
            if compiled_candidate.candidate_digest != expected_candidate_digest:
                raise ValueError("gate candidate digest is invalid")
            if self.candidate_digest != compiled_candidate.candidate_digest:
                raise ValueError("gate candidate digest does not match compilation")
            if self.evaluation.candidate_digest != self.candidate_digest and not (
                self.status == "BLOCK"
                and "evaluation:candidate_digest_mismatch" in self.reasons
            ):
                raise ValueError("gate evaluation targets another candidate")
        if self.status == "PASS":
            if self.minimum_provenance_level not in (None, "asserted"):
                raise ValueError(
                    "passing gate cannot rely on unverified external provenance"
                )
            if self.compilation.status != "compiled":
                raise ValueError("passing gate requires a compiled candidate")
            if self.verification.status != "valid":
                raise ValueError("passing gate requires valid receipt verification")
            if not self.verification.traces_verified:
                raise ValueError("passing gate requires exact trace replay")
            if self.evaluation.status != "pass":
                raise ValueError("passing gate requires a passing evaluation")
        expected_receipt_hash = canonical_digest(
            self.model_dump(mode="json", exclude={"receipt_hash"})
        )
        if self.receipt_hash != expected_receipt_hash:
            raise ValueError("gate receipt hash is invalid")
        return self


class SkillFile(ContractModel):
    """One byte-addressed file in a portable Agent Skill folder."""

    path: RelativeArtifactPath
    digest: Sha256Digest
    size_bytes: Annotated[int, Field(ge=0, le=100_000_000)]
    role: Literal["instructions", "metadata", "script", "reference", "asset", "other"]

    @model_validator(mode="after")
    def validate_portable_path(self) -> Self:
        if any(segment in ("", ".", "..") for segment in self.path.split("/")):
            raise ValueError("skill file path must be normalized and relative")
        return self


class SkillBom(ContractModel):
    """A non-executing inventory that binds the exact contents of one skill."""

    schema_version: Literal["awe.skill-bom.v1"] = "awe.skill-bom.v1"
    skill_name: Annotated[
        str,
        StringConstraints(
            min_length=1, max_length=64, pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$"
        ),
    ]
    files: Annotated[
        tuple[SkillFile, ...], Field(min_length=1, max_length=10_000, strict=False)
    ]
    external_urls: Annotated[
        tuple[ExternalUrl, ...], Field(max_length=10_000, strict=False)
    ] = ()
    skill_digest: Sha256Digest
    bom_digest: Sha256Digest

    @model_validator(mode="after")
    def validate_bom(self) -> Self:
        paths = tuple(item.path for item in self.files)
        if paths != tuple(sorted(paths)) or len(paths) != len(set(paths)):
            raise ValueError("skill BOM file paths must be unique and sorted")
        if not any(item.path == "SKILL.md" for item in self.files):
            raise ValueError("skill BOM requires SKILL.md")
        if self.external_urls != tuple(sorted(set(self.external_urls))):
            raise ValueError("skill BOM URLs must be unique and sorted")
        expected_skill_digest = canonical_digest(
            [item.model_dump(mode="json") for item in self.files]
        )
        if self.skill_digest != expected_skill_digest:
            raise ValueError("skill tree digest is invalid")
        expected_bom_digest = canonical_digest(
            self.model_dump(mode="json", exclude={"bom_digest"})
        )
        if self.bom_digest != expected_bom_digest:
            raise ValueError("skill BOM digest is invalid")
        return self


class EvidenceEnvelope(ContractModel):
    """Provider-neutral, provenance-bound envelope for one evidence artifact.

    A non-asserted level binds an external verification receipt by digest; the
    level is not itself a trust root. Consumers must separately trust or replay
    that verifier before treating the external receipt as authoritative.
    """

    schema_version: Literal["awe.evidence-envelope.v1"] = "awe.evidence-envelope.v1"
    evidence_id: TraceIdentifier
    artifact_kind: EvidenceArtifactKind
    producer: ToolName
    producer_version: ToolVersion
    producer_digest: Sha256Digest
    environment_digest: Sha256Digest
    provenance_level: ProvenanceLevel
    provenance_verification_digest: Sha256Digest | None = None
    repository_uri: RepositoryUri
    commit_sha: GitCommitSha
    captured_at: UtcDateTime
    payload: dict[str, Any]
    payload_digest: Sha256Digest

    @model_validator(mode="after")
    def validate_envelope(self) -> Self:
        if self.captured_at.utcoffset() != timedelta(0):
            raise ValueError("evidence capture time must include the UTC timezone")
        if canonical_digest(self.payload) != self.payload_digest:
            raise ValueError("evidence payload digest is invalid")
        if self.provenance_level == "asserted":
            if self.provenance_verification_digest is not None:
                raise ValueError("asserted provenance cannot claim verification")
        elif self.provenance_verification_digest is None:
            raise ValueError(
                "verified or attested provenance requires an external receipt digest"
            )
        if self.artifact_kind == "execution_traces":
            traces = self.payload.get("traces")
            if not isinstance(traces, list):
                raise ValueError("execution trace envelope requires a traces array")
            CompileRequest.model_validate({"traces": traces})
        elif self.artifact_kind == "evaluation_bundle":
            EvaluationBundle.model_validate(self.payload)
        elif self.artifact_kind == "evaluation_policy":
            EvaluationPolicy.model_validate(self.payload)
        elif self.artifact_kind == "gate_receipt":
            GateReceipt.model_validate(self.payload)
        elif self.artifact_kind == "skill_bom":
            SkillBom.model_validate(self.payload)
        return self


class EvidencePackage(ContractModel):
    """Content-addressed collection of envelopes from one repository revision."""

    schema_version: Literal["awe.evidence-package.v1"] = "awe.evidence-package.v1"
    package_id: TraceIdentifier
    repository_uri: RepositoryUri
    commit_sha: GitCommitSha
    created_at: UtcDateTime
    envelopes: Annotated[
        tuple[EvidenceEnvelope, ...],
        Field(min_length=1, max_length=1_000, strict=False),
    ]
    package_digest: Sha256Digest

    @model_validator(mode="after")
    def validate_package(self) -> Self:
        if self.created_at.utcoffset() != timedelta(0):
            raise ValueError("evidence package time must include the UTC timezone")
        evidence_ids = tuple(envelope.evidence_id for envelope in self.envelopes)
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("evidence package ids must be unique")
        if self.envelopes != tuple(
            sorted(self.envelopes, key=lambda item: item.evidence_id)
        ):
            raise ValueError("evidence package envelopes must be sorted by id")
        for envelope in self.envelopes:
            if envelope.repository_uri != self.repository_uri:
                raise ValueError("evidence envelope repository does not match package")
            if envelope.commit_sha != self.commit_sha:
                raise ValueError("evidence envelope commit does not match package")
            if envelope.captured_at > self.created_at:
                raise ValueError("evidence capture cannot follow package creation")
        expected = canonical_digest(
            self.model_dump(mode="json", exclude={"package_digest"})
        )
        if self.package_digest != expected:
            raise ValueError("evidence package digest is invalid")
        return self


class AdapterConformanceReceipt(ContractModel):
    """Deterministic result of validating a provider-neutral evidence envelope."""

    schema_version: Literal["awe.adapter-conformance.v1"] = "awe.adapter-conformance.v1"
    status: Literal["valid", "invalid"]
    envelope_digest: Sha256Digest
    artifact_kind: EvidenceArtifactKind | None = None
    reasons: Annotated[tuple[Reason, ...], Field(strict=False)] = ()
    receipt_hash: Sha256Digest

    @model_validator(mode="after")
    def validate_conformance(self) -> Self:
        if self.status == "valid" and self.reasons:
            raise ValueError("valid conformance receipt cannot contain reasons")
        if self.status == "valid" and self.artifact_kind is None:
            raise ValueError("valid conformance receipt requires artifact kind")
        if self.status == "invalid" and not self.reasons:
            raise ValueError("invalid conformance receipt requires reasons")
        expected = canonical_digest(
            self.model_dump(mode="json", exclude={"receipt_hash"})
        )
        if self.receipt_hash != expected:
            raise ValueError("adapter conformance receipt hash is invalid")
        return self


class CapabilitiesDocument(ContractModel):
    """Machine-readable statement of the installed offline core surface."""

    schema_version: Literal["awe.capabilities.v1"] = "awe.capabilities.v1"
    package_version: ToolVersion
    mode: Literal["offline_keyless"] = "offline_keyless"
    commands: Annotated[tuple[ToolName, ...], Field(min_length=1, strict=False)]
    gate_decisions: tuple[Literal["PASS", "REVIEW", "BLOCK", "ERROR"], ...] = (
        "PASS",
        "REVIEW",
        "BLOCK",
        "ERROR",
    )
    guarantees: Annotated[tuple[Identifier, ...], Field(strict=False)]
    exclusions: Annotated[tuple[Identifier, ...], Field(strict=False)]

    @model_validator(mode="after")
    def validate_sorted_sets(self) -> Self:
        for name, values in (
            ("commands", self.commands),
            ("guarantees", self.guarantees),
            ("exclusions", self.exclusions),
        ):
            if values != tuple(sorted(set(values))):
                raise ValueError(f"capability {name} must be unique and sorted")
        return self


class ExperimentTrial(ContractModel):
    """One frozen trial with quality, safety, token, cost, and trace evidence."""

    trial_id: TraceIdentifier
    case_id: TraceIdentifier
    succeeded: bool
    safety_violations: Annotated[int, Field(ge=0)] = 0
    latency_ms: Annotated[int, Field(ge=0)]
    cost_microusd: Annotated[int, Field(ge=0)]
    input_tokens: Annotated[int, Field(ge=0)]
    output_tokens: Annotated[int, Field(ge=0)]
    cached_input_tokens: Annotated[int, Field(ge=0)] = 0
    trace_id: TraceIdentifier | None = None
    grader_result_digest: Sha256Digest
    seed: Annotated[int, Field(ge=0, le=9_223_372_036_854_775_807)] | None = None

    @model_validator(mode="after")
    def validate_cached_tokens(self) -> Self:
        if self.cached_input_tokens > self.input_tokens:
            raise ValueError("cached input tokens cannot exceed input tokens")
        return self


class ExperimentRun(ContractModel):
    """Provider-neutral evidence shared by generic and telemetry importers."""

    experiment_id: TraceIdentifier
    repository_uri: RepositoryUri
    commit_sha: GitCommitSha
    subject_digest: Sha256Digest
    dataset_digest: Sha256Digest
    dataset_split_digest: Sha256Digest
    harness_name: ToolName
    harness_version: ToolVersion
    harness_digest: Sha256Digest
    strategy_name: ToolName
    strategy_digest: Sha256Digest
    model_provider: ToolName
    model_name: DisplayName
    model_config_digest: Sha256Digest
    environment_digest: Sha256Digest
    grader_digest: Sha256Digest
    trials: Annotated[
        tuple[ExperimentTrial, ...],
        Field(min_length=1, max_length=100_000, strict=False),
    ]

    @model_validator(mode="after")
    def validate_unique_trials(self) -> Self:
        trial_ids = [trial.trial_id for trial in self.trials]
        if len(trial_ids) != len(set(trial_ids)):
            raise ValueError("experiment trial ids must be unique")
        return self


class ExperimentManifest(ExperimentRun):
    """Content-addressed experiment evidence imported from one pinned format."""

    schema_version: Literal["awe.experiment-manifest.v1"] = "awe.experiment-manifest.v1"
    source_format: ToolName
    source_revision: ToolVersion
    manifest_digest: Sha256Digest

    @model_validator(mode="after")
    def validate_manifest_digest(self) -> Self:
        expected = canonical_digest(
            self.model_dump(mode="json", exclude={"manifest_digest"})
        )
        if self.manifest_digest != expected:
            raise ValueError("experiment manifest digest is invalid")
        return self


class SignedReceiptBundle(ContractModel):
    """A receipt artifact signed by one externally trusted Ed25519 identity."""

    schema_version: Literal["awe.signed-receipt-bundle.v1"] = (
        "awe.signed-receipt-bundle.v1"
    )
    signature_algorithm: Literal["ed25519"] = "ed25519"
    artifact_kind: Literal[
        "compilation",
        "verification",
        "evaluation",
        "experiment",
        "gate",
        "evidence_package",
        "promotion",
        "skill_bom",
    ]
    artifact_digest: Sha256Digest
    artifact: dict[str, Any]
    repository_uri: RepositoryUri
    commit_sha: GitCommitSha
    signer_id: SignerIdentity
    issued_at: UtcDateTime
    public_key_b64: Annotated[
        str,
        StringConstraints(
            min_length=44, max_length=44, pattern=r"^[A-Za-z0-9+/]{43}=$"
        ),
    ]
    public_key_fingerprint: Sha256Digest
    signature_b64: Annotated[
        str,
        StringConstraints(
            min_length=88, max_length=88, pattern=r"^[A-Za-z0-9+/]{86}==$"
        ),
    ]

    @model_validator(mode="after")
    def validate_bundle(self) -> Self:
        if self.issued_at.utcoffset() != timedelta(0):
            raise ValueError("issued_at must include the UTC timezone")
        if canonical_digest(self.artifact) != self.artifact_digest:
            raise ValueError("signed artifact digest is invalid")
        return self


class SignatureVerification(ContractModel):
    """Deterministic verification result against an explicit trusted key."""

    schema_version: Literal["awe.signature-verification.v1"] = (
        "awe.signature-verification.v1"
    )
    status: Literal["valid", "invalid"]
    bundle_digest: Sha256Digest
    signer_id: SignerIdentity
    public_key_fingerprint: Sha256Digest
    reasons: Annotated[tuple[Reason, ...], Field(strict=False)] = ()
    verification_hash: Sha256Digest

    @model_validator(mode="after")
    def validate_verification(self) -> Self:
        if self.status == "valid" and self.reasons:
            raise ValueError("valid signature verification cannot contain reasons")
        if self.status == "invalid" and not self.reasons:
            raise ValueError("invalid signature verification requires reasons")
        expected = canonical_digest(
            self.model_dump(mode="json", exclude={"verification_hash"})
        )
        if self.verification_hash != expected:
            raise ValueError("signature verification hash is invalid")
        return self


class EvaluateRequest(ContractModel):
    baseline: EvaluationBundle
    candidate: EvaluationBundle
    policy: EvaluationPolicy = EvaluationPolicy()


class PromotionReceipt(ContractModel):
    """Human decision bound to a verified compilation and evaluation chain."""

    schema_version: Literal["awe.promotion-receipt.v2"] = "awe.promotion-receipt.v2"
    candidate_digest: Sha256Digest
    compilation_receipt_hash: Sha256Digest
    input_bundle_digest: Sha256Digest
    verification_receipt_hash: Sha256Digest
    verification_status: Literal["valid", "invalid"]
    traces_verified: bool
    evaluation_receipt_hash: Sha256Digest
    evaluation_status: Literal["pass", "review", "block"]
    dataset_digest: Sha256Digest
    policy_digest: Sha256Digest
    decision: Literal["approved", "rejected"]
    actor_id: ActorIdentifier
    commit_sha: GitCommitSha
    issued_at: UtcDateTime
    rationale: Annotated[str, StringConstraints(min_length=1, max_length=1_024)]
    receipt_hash: Sha256Digest

    @model_validator(mode="after")
    def validate_promotion(self) -> Self:
        if self.issued_at.utcoffset() != timedelta(0):
            raise ValueError("issued_at must include the UTC timezone")
        if self.decision == "approved" and self.evaluation_status != "pass":
            raise ValueError("approval requires a passing evaluation receipt")
        if self.decision == "approved" and self.verification_status != "valid":
            raise ValueError("approval requires a valid verification receipt")
        if self.decision == "approved" and not self.traces_verified:
            raise ValueError("approval requires exact trace replay")
        expected_receipt_hash = canonical_digest(
            self.model_dump(mode="json", exclude={"receipt_hash"})
        )
        if self.receipt_hash != expected_receipt_hash:
            raise ValueError("promotion receipt hash is invalid")
        return self


class RedactionSummary(ContractModel):
    """Deterministic report for the built-in conservative JSON redactor."""

    schema_version: Literal["awe.redaction-summary.v1"] = "awe.redaction-summary.v1"
    policy_version: Literal["awe.redaction.v1"] = "awe.redaction.v1"
    input_digest: Sha256Digest
    output_digest: Sha256Digest
    changed: bool
    replacements: Annotated[int, Field(ge=0)]
    categories: dict[str, Annotated[int, Field(ge=0)]]


class RedactionPolicy(ContractModel):
    """Safe configurable key policy; regular expressions remain built in."""

    schema_version: Literal["awe.redaction-policy.v1"] = "awe.redaction-policy.v1"
    policy_id: TraceIdentifier
    policy_version: ToolVersion
    allowed_top_level_keys: Annotated[
        tuple[DisplayName, ...], Field(max_length=256, strict=False)
    ] = ()
    additional_sensitive_keys: Annotated[
        dict[DisplayName, RedactionCategory], Field(max_length=256)
    ] = Field(default_factory=dict)
    denied_keys: Annotated[
        dict[DisplayName, RedactionCategory], Field(max_length=256)
    ] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_normalized_keys(self) -> Self:
        collections = (
            self.allowed_top_level_keys,
            tuple(self.additional_sensitive_keys),
            tuple(self.denied_keys),
        )
        if any(key != key.lower() for keys in collections for key in keys):
            raise ValueError("redaction policy keys must be lowercase")
        if len(self.allowed_top_level_keys) != len(set(self.allowed_top_level_keys)):
            raise ValueError("allowed top-level keys must be unique")
        overlap = set(self.additional_sensitive_keys) & set(self.denied_keys)
        if overlap:
            raise ValueError("sensitive and denied key rules cannot overlap")
        return self


class DatasetConsentRecord(ContractModel):
    """Immutable consent state evaluated explicitly before governed export."""

    schema_version: Literal["awe.dataset-consent.v1"] = "awe.dataset-consent.v1"
    consent_id: TraceIdentifier
    data_subject_digest: Sha256Digest
    scopes: Annotated[
        tuple[DatasetScope, ...], Field(min_length=1, max_length=3, strict=False)
    ]
    status: Literal["active", "revoked"]
    actor_id: ActorIdentifier
    granted_at: UtcDateTime
    expires_at: UtcDateTime | None = None
    revoked_at: UtcDateTime | None = None

    @model_validator(mode="after")
    def validate_consent(self) -> Self:
        timestamps = (self.granted_at, self.expires_at, self.revoked_at)
        if any(
            value is not None and value.utcoffset() != timedelta(0)
            for value in timestamps
        ):
            raise ValueError("consent timestamps must include the UTC timezone")
        if len(self.scopes) != len(set(self.scopes)) or self.scopes != tuple(
            sorted(self.scopes)
        ):
            raise ValueError("consent scopes must be unique and sorted")
        if self.expires_at is not None and self.expires_at <= self.granted_at:
            raise ValueError("consent expiry must follow grant time")
        if self.status == "active" and self.revoked_at is not None:
            raise ValueError("active consent cannot have revoked_at")
        if self.status == "revoked" and self.revoked_at is None:
            raise ValueError("revoked consent requires revoked_at")
        if self.revoked_at is not None and self.revoked_at < self.granted_at:
            raise ValueError("consent revocation cannot precede grant time")
        return self


class GovernedRedactionSummary(ContractModel):
    """Auditable output of policy- and consent-gated dataset redaction."""

    schema_version: Literal["awe.governed-redaction-summary.v1"] = (
        "awe.governed-redaction-summary.v1"
    )
    input_digest: Sha256Digest
    output_digest: Sha256Digest
    changed: bool
    replacements: Annotated[int, Field(ge=0)]
    removed_fields: Annotated[int, Field(ge=0)]
    categories: dict[str, Annotated[int, Field(ge=0)]]
    policy_digest: Sha256Digest
    consent_record_digest: Sha256Digest
    consent_id: TraceIdentifier
    scope: DatasetScope
    evaluated_at: UtcDateTime


class VerifyRequest(ContractModel):
    receipt: CompilationReceipt
    traces: Annotated[tuple[ExecutionTrace, ...], Field(strict=False)] | None = None


class PromotionRequest(ContractModel):
    """Evidence inputs required to record a human promotion decision."""

    compilation: CompilationReceipt
    verification: ReceiptVerification
    traces: Annotated[tuple[ExecutionTrace, ...], Field(strict=False)]
    evaluation: EvaluationReceipt
    decision: Literal["approved", "rejected"]
    actor_id: ActorIdentifier
    commit_sha: GitCommitSha
    issued_at: UtcDateTime
    rationale: Annotated[str, StringConstraints(min_length=1, max_length=1_024)]


class HealthResponse(ContractModel):
    status: Literal["ok"] = "ok"
    mode: Literal["offline_keyless"] = "offline_keyless"


def canonical_json(value: Any) -> str:
    """Serialize JSON without platform- or insertion-order-dependent output."""

    if isinstance(value, BaseModel):
        value = value.model_dump(mode="json", exclude_none=False)
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def canonical_digest(value: Any) -> str:
    """Return a stable SHA-256 digest for a JSON-compatible value."""

    encoded = canonical_json(value).encode("utf-8")
    return f"sha256:{hashlib.sha256(encoded).hexdigest()}"
