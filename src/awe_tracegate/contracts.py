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
        "promotion",
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
