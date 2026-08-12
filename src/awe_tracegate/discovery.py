"""Consented, deterministic adapters for external coding-agent discovery runs.

This module parses frozen event streams and migration-check results. It never
starts an agent, imports migration code, connects to a database, or executes a
tool. Those side effects belong to an isolated external harness.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Annotated, Any, Literal, Self, cast

from pydantic import Field, model_validator

from .adapters import import_generic_evaluation
from .contracts import (
    ActorIdentifier,
    ContractModel,
    DisplayName,
    ExperimentManifest,
    ExperimentQualityEvidence,
    ExperimentRun,
    ExperimentTrial,
    GitCommitSha,
    RepositoryUri,
    Sha256Digest,
    TerminalOutcome,
    ToolName,
    ToolVersion,
    TraceIdentifier,
    TrialQualityEvidence,
    UtcDateTime,
    canonical_digest,
)

AgentRunner = Literal["codex", "claude_code", "external"]
TraceConsentScope = Literal["capture_trace", "evaluate_migration"]
AgentEventCategory = Literal[
    "session",
    "turn",
    "tool",
    "file_change",
    "message",
    "plan",
    "error",
    "other",
]
AgentEventStatus = Literal["started", "completed", "failed", "unknown"]
MigrationCheckName = Literal[
    "data_preservation",
    "forward_migration",
    "rollback",
    "tests",
]
FailureCategory = Literal[
    "agent_error",
    "data_preservation",
    "forward_migration",
    "infrastructure",
    "missing",
    "refusal",
    "rollback",
    "tests",
    "timeout",
]

_SUPPORTED_HANDOFF_SCHEMA = "awe.runtime-handoff.v2"
_EXPECTED_MIGRATION_CHECKS = (
    "data_preservation",
    "forward_migration",
    "rollback",
    "tests",
)
_MAX_TRACE_EVENTS = 100_000
_MAX_EVENT_BYTES = 1_048_576
MAX_AGENT_TRACE_BYTES = 33_554_432
_MAX_USAGE_VALUE = 9_223_372_036_854_775_807
_OPERATION_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("alembic_downgrade", re.compile(r"\balembic\s+downgrade\b", re.I)),
    ("alembic_upgrade", re.compile(r"\balembic\s+upgrade\b", re.I)),
    ("alembic_current", re.compile(r"\balembic\s+current\b", re.I)),
    ("data_check", re.compile(r"\b(?:psql|data[_ -]?preservation|checksum)\b", re.I)),
    ("tests", re.compile(r"\b(?:pytest|unittest|tox|nox)\b", re.I)),
)


class TraceCaptureConsent(ContractModel):
    """Asserted local consent carried by an approved Workspace handoff."""

    schema_version: Literal["awe.trace-capture-consent.v1"] = (
        "awe.trace-capture-consent.v1"
    )
    consent_id: TraceIdentifier
    run_id: TraceIdentifier
    actor_id: ActorIdentifier
    runner: AgentRunner
    scopes: Annotated[
        tuple[TraceConsentScope, ...], Field(min_length=1, max_length=2, strict=False)
    ]
    status: Literal["active", "revoked"]
    granted_at: UtcDateTime
    expires_at: UtcDateTime | None = None
    revoked_at: UtcDateTime | None = None

    @model_validator(mode="after")
    def validate_consent(self) -> Self:
        if self.scopes != tuple(sorted(set(self.scopes))):
            raise ValueError("trace consent scopes must be unique and sorted")
        if self.granted_at.utcoffset() is None:
            raise ValueError("trace consent grant time must include a timezone")
        if self.expires_at is not None:
            if self.expires_at.utcoffset() is None:
                raise ValueError("trace consent expiry must include a timezone")
            if self.expires_at <= self.granted_at:
                raise ValueError("trace consent expiry must follow its grant")
        if self.status == "active" and self.revoked_at is not None:
            raise ValueError("active trace consent cannot have a revocation time")
        if self.status == "revoked" and self.revoked_at is None:
            raise ValueError("revoked trace consent requires a revocation time")
        if self.revoked_at is not None:
            if self.revoked_at.utcoffset() is None:
                raise ValueError("trace consent revocation must include a timezone")
            if self.revoked_at < self.granted_at:
                raise ValueError("trace consent cannot be revoked before it is granted")
        return self


class AgentUsage(ContractModel):
    """Provider-reported usage; absent values remain zero rather than inferred."""

    input_tokens: Annotated[int, Field(ge=0, le=_MAX_USAGE_VALUE)] = 0
    cached_input_tokens: Annotated[int, Field(ge=0, le=_MAX_USAGE_VALUE)] = 0
    output_tokens: Annotated[int, Field(ge=0, le=_MAX_USAGE_VALUE)] = 0
    duration_ms: Annotated[int, Field(ge=0, le=_MAX_USAGE_VALUE)] = 0
    cost_microusd: Annotated[int, Field(ge=0, le=_MAX_USAGE_VALUE)] = 0

    @model_validator(mode="after")
    def validate_cached_tokens(self) -> Self:
        if self.cached_input_tokens > self.input_tokens:
            raise ValueError("cached input tokens cannot exceed input tokens")
        return self


class AgentTraceEvent(ContractModel):
    """A redacted event identity; raw prompt, command, and output are not retained."""

    sequence: Annotated[int, Field(ge=0, lt=_MAX_TRACE_EVENTS)]
    provider_event_type: ToolName
    category: AgentEventCategory
    status: AgentEventStatus
    operation: ToolName | None = None
    payload_digest: Sha256Digest


class AgentTraceReceipt(ContractModel):
    """Content-addressed trace receipt bound to one consented handoff and SHA."""

    schema_version: Literal["awe.agent-trace-receipt.v1"] = "awe.agent-trace-receipt.v1"
    source_format: Literal["codex.exec-jsonl", "claude.stream-json", "awe.agent-jsonl"]
    source_revision: ToolVersion
    run_id: TraceIdentifier
    runner: AgentRunner
    repository_uri: RepositoryUri
    commit_sha: GitCommitSha
    revision_binding: Literal["caller_asserted"] = "caller_asserted"
    handoff_digest: Sha256Digest
    consent_digest: Sha256Digest
    consent_scopes: Annotated[
        tuple[TraceConsentScope, ...], Field(min_length=1, max_length=2, strict=False)
    ]
    terminal_outcome: TerminalOutcome
    usage: AgentUsage
    events: Annotated[
        tuple[AgentTraceEvent, ...],
        Field(min_length=1, max_length=_MAX_TRACE_EVENTS, strict=False),
    ]
    trace_digest: Sha256Digest

    @model_validator(mode="after")
    def validate_trace(self) -> Self:
        if tuple(event.sequence for event in self.events) != tuple(
            range(len(self.events))
        ):
            raise ValueError("agent trace event sequences must be contiguous")
        if self.consent_scopes != tuple(sorted(set(self.consent_scopes))):
            raise ValueError("agent trace consent scopes must be unique and sorted")
        expected = canonical_digest(
            self.model_dump(mode="json", exclude={"trace_digest"})
        )
        if self.trace_digest != expected:
            raise ValueError("agent trace digest is invalid")
        return self


class MigrationCheck(ContractModel):
    """One externally executed PostgreSQL/Alembic assertion."""

    name: MigrationCheckName
    outcome: TerminalOutcome
    duration_ms: Annotated[int, Field(ge=0)]
    evidence_digest: Sha256Digest


class MigrationTrial(ContractModel):
    """One frozen migration case and its four required evidence lanes."""

    trial_id: TraceIdentifier
    case_id: TraceIdentifier
    seed: Annotated[int, Field(ge=0, le=9_223_372_036_854_775_807)] | None = None
    checks: Annotated[
        tuple[MigrationCheck, ...], Field(min_length=4, max_length=4, strict=False)
    ]
    cost_microusd: Annotated[int, Field(ge=0)] = 0
    input_tokens: Annotated[int, Field(ge=0)] = 0
    cached_input_tokens: Annotated[int, Field(ge=0)] = 0
    output_tokens: Annotated[int, Field(ge=0)] = 0

    @model_validator(mode="after")
    def validate_checks(self) -> Self:
        names = tuple(check.name for check in self.checks)
        if names != _EXPECTED_MIGRATION_CHECKS:
            raise ValueError(
                "migration checks must contain data_preservation, "
                "forward_migration, rollback, and tests in sorted order"
            )
        if self.cached_input_tokens > self.input_tokens:
            raise ValueError("cached input tokens cannot exceed input tokens")
        return self


class PostgresAlembicExperiment(ContractModel):
    """Frozen input emitted by an isolated migration harness."""

    schema_version: Literal["awe.postgres-alembic-experiment.v1"] = (
        "awe.postgres-alembic-experiment.v1"
    )
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
        tuple[MigrationTrial, ...],
        Field(min_length=1, max_length=10_000, strict=False),
    ]

    @model_validator(mode="after")
    def validate_trials(self) -> Self:
        trial_ids = tuple(trial.trial_id for trial in self.trials)
        if trial_ids != tuple(sorted(set(trial_ids))):
            raise ValueError("migration trial ids must be unique and sorted")
        return self


class FailureCluster(ContractModel):
    """Deterministic grouping by evidence lane and terminal outcome."""

    cluster_id: Sha256Digest
    category: FailureCategory
    operation: ToolName
    terminal_outcome: TerminalOutcome
    occurrence_count: Annotated[int, Field(ge=1)]
    evidence_digests: Annotated[
        tuple[Sha256Digest, ...], Field(min_length=1, strict=False)
    ]


class FailureClusterReport(ContractModel):
    """Content-addressed failure summary with no model-generated diagnosis."""

    schema_version: Literal["awe.failure-cluster-report.v1"] = (
        "awe.failure-cluster-report.v1"
    )
    agent_trace_digest: Sha256Digest
    experiment_digest: Sha256Digest
    clusters: Annotated[tuple[FailureCluster, ...], Field(strict=False)] = ()
    report_digest: Sha256Digest

    @model_validator(mode="after")
    def validate_report(self) -> Self:
        cluster_ids = tuple(cluster.cluster_id for cluster in self.clusters)
        if cluster_ids != tuple(sorted(set(cluster_ids))):
            raise ValueError("failure clusters must be unique and sorted")
        expected = canonical_digest(
            self.model_dump(mode="json", exclude={"report_digest"})
        )
        if self.report_digest != expected:
            raise ValueError("failure cluster report digest is invalid")
        return self


class MigrationDiscoveryBundle(ContractModel):
    """Portable output sent to TraceGate comparison and Gate v2 workflows."""

    schema_version: Literal["awe.migration-discovery-bundle.v1"] = (
        "awe.migration-discovery-bundle.v1"
    )
    agent_trace: AgentTraceReceipt
    experiment_manifest: ExperimentManifest
    quality_evidence: ExperimentQualityEvidence
    failure_report: FailureClusterReport
    bundle_digest: Sha256Digest

    @model_validator(mode="after")
    def validate_bundle(self) -> Self:
        if self.agent_trace.repository_uri != self.experiment_manifest.repository_uri:
            raise ValueError("agent trace and migration experiment repositories differ")
        if self.agent_trace.commit_sha != self.experiment_manifest.commit_sha:
            raise ValueError("agent trace and migration experiment commits differ")
        if (
            self.quality_evidence.manifest_digest
            != self.experiment_manifest.manifest_digest
        ):
            raise ValueError("quality evidence targets another experiment manifest")
        if self.failure_report.agent_trace_digest != self.agent_trace.trace_digest:
            raise ValueError("failure report targets another agent trace")
        if (
            self.failure_report.experiment_digest
            != self.experiment_manifest.manifest_digest
        ):
            raise ValueError("failure report targets another experiment manifest")
        expected = canonical_digest(
            self.model_dump(mode="json", exclude={"bundle_digest"})
        )
        if self.bundle_digest != expected:
            raise ValueError("migration discovery bundle digest is invalid")
        return self


def _required_string(value: object, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _active_consent(
    handoff: Mapping[str, Any], *, runner: AgentRunner, evaluated_at: datetime
) -> TraceCaptureConsent:
    if handoff.get("schema_version") != _SUPPORTED_HANDOFF_SCHEMA:
        raise ValueError("agent trace import requires an AWE Workspace handoff v2")
    if handoff.get("state") not in {"handoff_ready", "checkpointed"}:
        raise ValueError("agent trace import requires an approved handoff state")
    if handoff.get("runner") != runner:
        raise ValueError("agent trace runner does not match the approved handoff")
    consent = TraceCaptureConsent.model_validate(handoff.get("trace_consent"))
    if consent.run_id != handoff.get("run_id"):
        raise ValueError("trace consent does not bind the handoff run")
    if consent.runner != runner:
        raise ValueError("trace consent runner does not match the handoff")
    if consent.status != "active":
        raise ValueError("trace consent is revoked")
    if evaluated_at.utcoffset() is None:
        raise ValueError("trace evaluation time must include a timezone")
    if evaluated_at < consent.granted_at:
        raise ValueError("trace consent is not active yet")
    if consent.expires_at is not None and evaluated_at >= consent.expires_at:
        raise ValueError("trace consent has expired")
    if "capture_trace" not in consent.scopes:
        raise ValueError("trace consent must grant capture_trace")
    return consent


def _event_status(event_type: str, event: Mapping[str, Any]) -> AgentEventStatus:
    if event_type.endswith(".started"):
        return "started"
    if event_type.endswith(".completed"):
        item = event.get("item")
        if isinstance(item, Mapping) and item.get("status") in {"failed", "error"}:
            return "failed"
        return "completed"
    if event_type.endswith(".failed") or event_type in {"error", "result_error"}:
        return "failed"
    status = event.get("status")
    if status in {"started", "completed", "failed"}:
        return cast(AgentEventStatus, status)
    return "unknown"


def _command_operation(command: object) -> ToolName | None:
    if not isinstance(command, str):
        return None
    for operation, pattern in _OPERATION_PATTERNS:
        if pattern.search(command):
            return operation
    return "command"


def _codex_event(
    event: Mapping[str, Any],
) -> tuple[str, AgentEventCategory, ToolName | None]:
    event_type = _required_string(event.get("type"), "Codex event type")
    category: AgentEventCategory = "other"
    operation: ToolName | None = None
    if event_type.startswith("thread."):
        category = "session"
    elif event_type.startswith("turn."):
        category = "turn"
    elif event_type == "error":
        category = "error"
    elif event_type.startswith("item."):
        item = event.get("item")
        if not isinstance(item, Mapping):
            raise ValueError("Codex item event requires an item object")
        item_type = _required_string(item.get("type"), "Codex item type")
        if item_type in {"command_execution", "mcp_tool_call", "web_search"}:
            category = "tool"
            operation = _command_operation(item.get("command"))
        elif item_type == "file_change":
            category = "file_change"
            operation = "file_change"
        elif item_type == "plan_update":
            category = "plan"
        elif item_type in {"agent_message", "reasoning"}:
            category = "message"
    return event_type, category, operation


def _claude_event(
    event: Mapping[str, Any],
) -> tuple[str, AgentEventCategory, ToolName | None]:
    event_type = _required_string(event.get("type"), "Claude event type")
    subtype = event.get("subtype")
    provider_type = event_type
    if isinstance(subtype, str) and subtype:
        provider_type = f"{event_type}.{subtype}"
    if event_type == "system" and subtype == "init":
        return provider_type, "session", None
    if event_type == "result":
        return provider_type, "turn", None
    if event_type in {"assistant", "user"}:
        return provider_type, "message", None
    if event_type == "error":
        return provider_type, "error", None
    return provider_type, "other", None


def _usage_from_events(
    events: Sequence[Mapping[str, Any]], *, source_format: str
) -> AgentUsage:
    if source_format == "codex.exec-jsonl":
        for event in reversed(events):
            usage = event.get("usage")
            if event.get("type") != "turn.completed" or not isinstance(usage, Mapping):
                continue
            return AgentUsage(
                input_tokens=_nonnegative_int(usage.get("input_tokens")),
                cached_input_tokens=_nonnegative_int(usage.get("cached_input_tokens")),
                output_tokens=_nonnegative_int(usage.get("output_tokens")),
            )
        return AgentUsage()
    if source_format == "claude.stream-json":
        for event in reversed(events):
            if event.get("type") != "result":
                continue
            usage = event.get("usage")
            usage_map = usage if isinstance(usage, Mapping) else {}
            return AgentUsage(
                input_tokens=_nonnegative_int(usage_map.get("input_tokens")),
                output_tokens=_nonnegative_int(usage_map.get("output_tokens")),
                duration_ms=_nonnegative_int(event.get("duration_ms")),
                cost_microusd=_microusd(event.get("total_cost_usd")),
            )
    return AgentUsage()


def _nonnegative_int(value: object) -> int:
    if value is None:
        return 0
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < 0
        or value > _MAX_USAGE_VALUE
    ):
        raise ValueError("agent usage values must be non-negative integers")
    return value


def _microusd(value: object) -> int:
    if value is None:
        return 0
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise ValueError("agent cost must be a non-negative decimal") from error
    if not amount.is_finite() or amount < 0 or amount * 1_000_000 > _MAX_USAGE_VALUE:
        raise ValueError("agent cost must be a non-negative decimal")
    return int(amount * 1_000_000)


def _terminal_outcome(
    events: Sequence[Mapping[str, Any]], *, source_format: str
) -> TerminalOutcome:
    if source_format == "codex.exec-jsonl":
        types = [event.get("type") for event in events]
        if "turn.failed" in types or "error" in types:
            return "failure"
        if "turn.completed" in types:
            return "success"
        return "missing"
    if source_format == "claude.stream-json":
        for event in reversed(events):
            if event.get("type") != "result":
                continue
            if event.get("subtype") == "success" and event.get("is_error") is False:
                return "success"
            return "failure"
        return "missing"
    for event in reversed(events):
        outcome = event.get("terminal_outcome")
        if outcome in {
            "success",
            "failure",
            "timeout",
            "refusal",
            "infrastructure_error",
            "missing",
        }:
            return cast(TerminalOutcome, outcome)
    return "missing"


def import_agent_trace(
    lines: Iterable[bytes | str],
    *,
    source_format: Literal["codex.exec-jsonl", "claude.stream-json", "awe.agent-jsonl"],
    handoff: Mapping[str, Any],
    repository_uri: str,
    commit_sha: str,
    evaluated_at: datetime,
) -> AgentTraceReceipt:
    """Normalize one consented agent event stream without retaining raw content."""

    runner: AgentRunner
    if source_format == "codex.exec-jsonl":
        runner = "codex"
    elif source_format == "claude.stream-json":
        runner = "claude_code"
    else:
        runner = "external"
    consent = _active_consent(handoff, runner=runner, evaluated_at=evaluated_at)

    raw_events: list[Mapping[str, Any]] = []
    normalized: list[AgentTraceEvent] = []
    total_bytes = 0
    for line in lines:
        encoded = line.encode("utf-8") if isinstance(line, str) else line
        total_bytes += len(encoded)
        if total_bytes > MAX_AGENT_TRACE_BYTES:
            raise ValueError("agent trace exceeds the 32 MB total input limit")
        if len(encoded) > _MAX_EVENT_BYTES:
            raise ValueError("agent trace event exceeds the 1 MB limit")
        if not encoded.strip():
            continue
        if len(normalized) >= _MAX_TRACE_EVENTS:
            raise ValueError("agent trace exceeds the 100,000 event limit")
        try:
            event = json.loads(encoded, object_pairs_hook=_unique_json_object)
        except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as error:
            raise ValueError("agent trace contains invalid JSONL") from error
        if not isinstance(event, Mapping):
            raise ValueError("agent trace events must be JSON objects")
        if source_format == "codex.exec-jsonl":
            provider_type, category, operation = _codex_event(event)
        elif source_format == "claude.stream-json":
            provider_type, category, operation = _claude_event(event)
        else:
            provider_type = _required_string(event.get("type"), "Agent event type")
            category_value = event.get("category", "other")
            if category_value not in {
                "session",
                "turn",
                "tool",
                "file_change",
                "message",
                "plan",
                "error",
                "other",
            }:
                raise ValueError("generic agent event category is unsupported")
            category = category_value
            operation_value = event.get("operation")
            operation = operation_value
            if operation is not None and not isinstance(operation, str):
                raise ValueError("generic agent event operation must be a string")
        raw_events.append(event)
        normalized.append(
            AgentTraceEvent(
                sequence=len(normalized),
                provider_event_type=provider_type,
                category=category,
                status=_event_status(provider_type, event),
                operation=operation,
                payload_digest=canonical_digest(event),
            )
        )
    if not normalized:
        raise ValueError("agent trace must contain at least one event")

    usage = _usage_from_events(raw_events, source_format=source_format)
    payload: dict[str, Any] = {
        "schema_version": "awe.agent-trace-receipt.v1",
        "source_format": source_format,
        "source_revision": "v1",
        "run_id": _required_string(handoff.get("run_id"), "Handoff run id"),
        "runner": runner,
        "repository_uri": repository_uri,
        "commit_sha": commit_sha,
        "revision_binding": "caller_asserted",
        "handoff_digest": canonical_digest(handoff),
        "consent_digest": canonical_digest(consent),
        "consent_scopes": consent.scopes,
        "terminal_outcome": _terminal_outcome(raw_events, source_format=source_format),
        "usage": usage.model_dump(mode="json"),
        "events": tuple(event.model_dump(mode="json") for event in normalized),
    }
    return AgentTraceReceipt.model_validate(
        {**payload, "trace_digest": canonical_digest(payload)}
    )


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f"agent trace JSON contains duplicate key: {key}")
        result[key] = value
    return result


def _migration_terminal_outcome(checks: Sequence[MigrationCheck]) -> TerminalOutcome:
    outcomes = {check.outcome for check in checks}
    if outcomes == {"success"}:
        return "success"
    for outcome in (
        "missing",
        "infrastructure_error",
        "timeout",
        "refusal",
        "failure",
    ):
        if outcome in outcomes:
            return cast(TerminalOutcome, outcome)
    raise ValueError("migration check contains an unsupported terminal outcome")


def _failure_category(check: MigrationCheck) -> FailureCategory:
    if check.outcome == "timeout":
        return "timeout"
    if check.outcome == "refusal":
        return "refusal"
    if check.outcome == "infrastructure_error":
        return "infrastructure"
    if check.outcome == "missing":
        return "missing"
    return check.name


def _failure_report(
    trace: AgentTraceReceipt,
    manifest: ExperimentManifest,
    migration: PostgresAlembicExperiment,
) -> FailureClusterReport:
    grouped: dict[
        tuple[FailureCategory, ToolName, TerminalOutcome], list[Sha256Digest]
    ] = defaultdict(list)
    for event in trace.events:
        if event.status == "failed":
            operation = event.operation or "agent_event"
            grouped[("agent_error", operation, "failure")].append(event.payload_digest)
    for trial in migration.trials:
        for check in trial.checks:
            if check.outcome == "success":
                continue
            grouped[(_failure_category(check), check.name, check.outcome)].append(
                check.evidence_digest
            )

    clusters: list[FailureCluster] = []
    for (category, operation, outcome), digests in sorted(grouped.items()):
        unique_digests = tuple(sorted(set(digests)))
        identity = {
            "category": category,
            "operation": operation,
            "terminal_outcome": outcome,
            "evidence_digests": unique_digests,
        }
        clusters.append(
            FailureCluster(
                cluster_id=canonical_digest(identity),
                category=category,
                operation=operation,
                terminal_outcome=outcome,
                occurrence_count=len(digests),
                evidence_digests=unique_digests,
            )
        )
    clusters.sort(key=lambda cluster: cluster.cluster_id)
    payload = {
        "schema_version": "awe.failure-cluster-report.v1",
        "agent_trace_digest": trace.trace_digest,
        "experiment_digest": manifest.manifest_digest,
        "clusters": tuple(cluster.model_dump(mode="json") for cluster in clusters),
    }
    return FailureClusterReport.model_validate(
        {**payload, "report_digest": canonical_digest(payload)}
    )


def build_migration_discovery_bundle(
    trace: AgentTraceReceipt,
    migration: PostgresAlembicExperiment,
) -> MigrationDiscoveryBundle:
    """Project isolated migration results into existing TraceGate artifacts."""

    if trace.repository_uri != migration.repository_uri:
        raise ValueError("agent trace and migration results repositories differ")
    if trace.commit_sha != migration.commit_sha:
        raise ValueError("agent trace and migration results commits differ")
    if "evaluate_migration" not in trace.consent_scopes:
        raise ValueError("migration bundle requires evaluate_migration consent")

    experiment_trials: list[ExperimentTrial] = []
    quality_trials: list[TrialQualityEvidence] = []
    for trial in migration.trials:
        terminal_outcome = _migration_terminal_outcome(trial.checks)
        experiment_trials.append(
            ExperimentTrial(
                trial_id=trial.trial_id,
                case_id=trial.case_id,
                succeeded=terminal_outcome == "success",
                safety_violations=int(
                    next(
                        check.outcome
                        for check in trial.checks
                        if check.name == "data_preservation"
                    )
                    != "success"
                ),
                latency_ms=sum(check.duration_ms for check in trial.checks),
                cost_microusd=trial.cost_microusd,
                input_tokens=trial.input_tokens,
                output_tokens=trial.output_tokens,
                cached_input_tokens=trial.cached_input_tokens,
                trace_id=trace.trace_digest,
                grader_result_digest=canonical_digest(
                    tuple(check.model_dump(mode="json") for check in trial.checks)
                ),
                seed=trial.seed,
            )
        )
        quality_trials.append(
            TrialQualityEvidence(
                trial_id=trial.trial_id,
                terminal_outcome=terminal_outcome,
            )
        )

    run = ExperimentRun(
        experiment_id=migration.experiment_id,
        repository_uri=migration.repository_uri,
        commit_sha=migration.commit_sha,
        subject_digest=migration.subject_digest,
        dataset_digest=migration.dataset_digest,
        dataset_split_digest=migration.dataset_split_digest,
        harness_name=migration.harness_name,
        harness_version=migration.harness_version,
        harness_digest=migration.harness_digest,
        strategy_name=migration.strategy_name,
        strategy_digest=migration.strategy_digest,
        model_provider=migration.model_provider,
        model_name=migration.model_name,
        model_config_digest=migration.model_config_digest,
        environment_digest=migration.environment_digest,
        grader_digest=migration.grader_digest,
        trials=tuple(experiment_trials),
    )
    manifest = import_generic_evaluation(run.model_dump(mode="json"))
    quality_payload = {
        "schema_version": "awe.experiment-quality-evidence.v1",
        "manifest_digest": manifest.manifest_digest,
        "trials": tuple(trial.model_dump(mode="json") for trial in quality_trials),
    }
    quality = ExperimentQualityEvidence.model_validate(
        {**quality_payload, "evidence_digest": canonical_digest(quality_payload)}
    )
    failures = _failure_report(trace, manifest, migration)
    bundle_payload = {
        "schema_version": "awe.migration-discovery-bundle.v1",
        "agent_trace": trace.model_dump(mode="json"),
        "experiment_manifest": manifest.model_dump(mode="json"),
        "quality_evidence": quality.model_dump(mode="json"),
        "failure_report": failures.model_dump(mode="json"),
    }
    return MigrationDiscoveryBundle.model_validate(
        {**bundle_payload, "bundle_digest": canonical_digest(bundle_payload)}
    )
