"""Consent-bound Discovery Loop intervention and replay contracts.

This module deliberately stops at a portable replay request.  It does not
start an agent, execute a migration, or mutate a repository.  An external
runner consumes the approved request and must return a new, SHA-bound
experiment bundle for TraceGate to compare.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Annotated, Literal, Self, cast

from pydantic import Field, StringConstraints, TypeAdapter, model_validator

from .contracts import (
    ActorIdentifier,
    ContractModel,
    GitCommitSha,
    RepositoryUri,
    Sha256Digest,
    TraceIdentifier,
    UtcDateTime,
    canonical_digest,
)
from .discovery import FailureClusterReport, MigrationDiscoveryBundle

InterventionKind = Literal[
    "prompt_revision",
    "tool_policy",
    "workflow_guard",
    "test_expansion",
]
InterventionStatus = Literal["proposed", "approved", "rejected", "replayed"]
ApprovalDecision = Literal["approved", "rejected"]

_MAX_TEXT = 2_000


def _json_payload(payload: dict[str, object]) -> dict[str, object]:
    """Convert datetime/tuple values to the canonical JSON representation."""

    return cast(
        dict[str, object],
        TypeAdapter(dict[str, object]).dump_python(payload, mode="json"),
    )


class DiscoveryIntervention(ContractModel):
    """A human-readable, content-addressed change proposal for one cluster."""

    schema_version: Literal["awe.discovery-intervention.v1"] = (
        "awe.discovery-intervention.v1"
    )
    intervention_id: TraceIdentifier
    source_bundle_digest: Sha256Digest
    source_cluster_id: Sha256Digest
    kind: InterventionKind
    hypothesis: Annotated[str, StringConstraints(min_length=1, max_length=_MAX_TEXT)]
    change_digest: Sha256Digest
    target_case_ids: Annotated[
        tuple[TraceIdentifier, ...],
        Field(min_length=1, max_length=10_000, strict=False),
    ]
    proposer_id: ActorIdentifier
    proposed_at: UtcDateTime
    status: InterventionStatus = "proposed"
    intervention_digest: Sha256Digest

    @model_validator(mode="after")
    def validate_intervention(self) -> Self:
        if self.target_case_ids != tuple(sorted(set(self.target_case_ids))):
            raise ValueError("intervention target cases must be unique and sorted")
        if self.proposed_at.utcoffset() != timedelta(0):
            raise ValueError("intervention time must be UTC")
        expected = canonical_digest(
            self.model_dump(mode="json", exclude={"intervention_digest"})
        )
        if self.intervention_digest != expected:
            raise ValueError("intervention digest is invalid")
        return self


class InterventionApproval(ContractModel):
    """An explicit human approval; proposal authors cannot self-approve."""

    schema_version: Literal["awe.intervention-approval.v1"] = (
        "awe.intervention-approval.v1"
    )
    approval_id: TraceIdentifier
    intervention_id: TraceIdentifier
    reviewer_id: ActorIdentifier
    decision: ApprovalDecision
    reviewed_at: UtcDateTime
    expires_at: UtcDateTime | None = None
    rationale: Annotated[str, StringConstraints(min_length=1, max_length=_MAX_TEXT)]
    approval_digest: Sha256Digest

    @model_validator(mode="after")
    def validate_approval(self) -> Self:
        if self.expires_at is not None:
            if self.expires_at.utcoffset() != timedelta(0):
                raise ValueError("approval expiry must be UTC")
            if self.expires_at <= self.reviewed_at:
                raise ValueError("approval expiry must follow review time")
        expected = canonical_digest(
            self.model_dump(mode="json", exclude={"approval_digest"})
        )
        if self.approval_digest != expected:
            raise ValueError("approval digest is invalid")
        return self


class DiscoveryReplayRequest(ContractModel):
    """External-runner input that binds intervention, approval, and held inputs."""

    schema_version: Literal["awe.discovery-replay-request.v1"] = (
        "awe.discovery-replay-request.v1"
    )
    request_id: TraceIdentifier
    intervention: DiscoveryIntervention
    approval: InterventionApproval
    repository_uri: RepositoryUri
    commit_sha: GitCommitSha
    baseline_manifest_digest: Sha256Digest
    heldout_split_digest: Sha256Digest
    prepared_at: UtcDateTime
    execution: Literal["external_runner_required"] = "external_runner_required"
    request_digest: Sha256Digest

    @model_validator(mode="after")
    def validate_request(self) -> Self:
        if self.approval.intervention_id != self.intervention.intervention_id:
            raise ValueError("approval targets another intervention")
        if self.approval.decision != "approved":
            raise ValueError("replay requires an approved intervention")
        if self.prepared_at.utcoffset() != timedelta(0):
            raise ValueError("replay preparation time must be UTC")
        if (
            self.approval.expires_at is not None
            and self.prepared_at >= self.approval.expires_at
        ):
            raise ValueError("intervention approval has expired")
        if self.intervention.status != "approved":
            raise ValueError("replay requires an approved intervention status")
        expected = canonical_digest(
            self.model_dump(mode="json", exclude={"request_digest"})
        )
        if self.request_digest != expected:
            raise ValueError("replay request digest is invalid")
        return self


def propose_intervention(
    report: FailureClusterReport,
    bundle: MigrationDiscoveryBundle,
    *,
    cluster_id: Sha256Digest,
    intervention_id: TraceIdentifier,
    kind: InterventionKind,
    hypothesis: str,
    change_digest: Sha256Digest,
    target_case_ids: tuple[TraceIdentifier, ...],
    proposer_id: ActorIdentifier,
    proposed_at: datetime,
) -> DiscoveryIntervention:
    """Create a proposal from a known failure cluster without inventing evidence."""

    if report.report_digest != bundle.failure_report.report_digest:
        raise ValueError("failure report does not belong to the supplied bundle")
    if cluster_id not in {cluster.cluster_id for cluster in report.clusters}:
        raise ValueError("intervention cluster is not present in the failure report")
    payload = {
        "schema_version": "awe.discovery-intervention.v1",
        "intervention_id": intervention_id,
        "source_bundle_digest": bundle.bundle_digest,
        "source_cluster_id": cluster_id,
        "kind": kind,
        "hypothesis": hypothesis,
        "change_digest": change_digest,
        "target_case_ids": tuple(sorted(set(target_case_ids))),
        "proposer_id": proposer_id,
        "proposed_at": proposed_at,
        "status": "proposed",
    }
    canonical = _json_payload(payload)
    return DiscoveryIntervention.model_validate(
        {**canonical, "intervention_digest": canonical_digest(canonical)}
    )


def approve_intervention(
    intervention: DiscoveryIntervention,
    *,
    approval_id: TraceIdentifier,
    reviewer_id: ActorIdentifier,
    decision: ApprovalDecision,
    reviewed_at: datetime,
    rationale: str,
    expires_at: datetime | None = None,
) -> tuple[DiscoveryIntervention, InterventionApproval]:
    """Record a human approval and return an immutable proposal version."""

    if reviewer_id == intervention.proposer_id:
        raise ValueError("intervention proposer cannot self-approve")
    approval_payload = {
        "schema_version": "awe.intervention-approval.v1",
        "approval_id": approval_id,
        "intervention_id": intervention.intervention_id,
        "reviewer_id": reviewer_id,
        "decision": decision,
        "reviewed_at": reviewed_at,
        "expires_at": expires_at,
        "rationale": rationale,
    }
    canonical_approval = _json_payload(approval_payload)
    approval = InterventionApproval.model_validate(
        {
            **canonical_approval,
            "approval_digest": canonical_digest(canonical_approval),
        }
    )
    status: InterventionStatus = "approved" if decision == "approved" else "rejected"
    proposal_payload = intervention.model_dump(
        mode="json", exclude={"intervention_digest"}
    )
    proposal_payload["status"] = status
    approved = DiscoveryIntervention.model_validate(
        {**proposal_payload, "intervention_digest": canonical_digest(proposal_payload)}
    )
    return approved, approval


def prepare_replay_request(
    intervention: DiscoveryIntervention,
    approval: InterventionApproval,
    *,
    request_id: TraceIdentifier,
    repository_uri: RepositoryUri,
    commit_sha: GitCommitSha,
    baseline_manifest_digest: Sha256Digest,
    heldout_split_digest: Sha256Digest,
    prepared_at: datetime,
) -> DiscoveryReplayRequest:
    """Prepare a replay handoff; execution remains outside the trusted core."""

    payload = {
        "schema_version": "awe.discovery-replay-request.v1",
        "request_id": request_id,
        "intervention": intervention.model_dump(mode="json"),
        "approval": approval.model_dump(mode="json"),
        "repository_uri": repository_uri,
        "commit_sha": commit_sha,
        "baseline_manifest_digest": baseline_manifest_digest,
        "heldout_split_digest": heldout_split_digest,
        "prepared_at": prepared_at,
        "execution": "external_runner_required",
    }
    canonical = _json_payload(payload)
    return DiscoveryReplayRequest.model_validate(
        {**canonical, "request_digest": canonical_digest(canonical)}
    )
