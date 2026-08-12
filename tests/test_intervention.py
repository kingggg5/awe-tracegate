from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from awe_tracegate.discovery import build_migration_discovery_bundle
from awe_tracegate.intervention import (
    approve_intervention,
    prepare_replay_request,
    propose_intervention,
)
from tests.test_discovery import _migration, _trace

NOW = datetime(2026, 8, 11, 4, 0, tzinfo=UTC)
DIGEST = "sha256:" + "a" * 64


def _proposal():
    bundle = build_migration_discovery_bundle(_trace(), _migration())
    report = bundle.failure_report
    cluster = report.clusters[0]
    intervention = propose_intervention(
        report,
        bundle,
        cluster_id=cluster.cluster_id,
        intervention_id="intervention-rollback-guard",
        kind="workflow_guard",
        hypothesis="Require an explicit downgrade verification before promotion.",
        change_digest=DIGEST,
        target_case_ids=("case-1",),
        proposer_id="agent-reviewer",
        proposed_at=NOW,
    )
    return bundle, intervention


def test_intervention_requires_cluster_and_is_deterministic() -> None:
    bundle, first = _proposal()
    second = propose_intervention(
        bundle.failure_report,
        bundle,
        cluster_id=first.source_cluster_id,
        intervention_id=first.intervention_id,
        kind=first.kind,
        hypothesis=first.hypothesis,
        change_digest=first.change_digest,
        target_case_ids=first.target_case_ids,
        proposer_id=first.proposer_id,
        proposed_at=NOW,
    )
    assert first == second


def test_approval_requires_independent_reviewer_and_prepares_replay() -> None:
    bundle, proposal = _proposal()
    approved, approval = approve_intervention(
        proposal,
        approval_id="approval-rollback-guard",
        reviewer_id="human-reviewer",
        decision="approved",
        reviewed_at=NOW + timedelta(minutes=1),
        expires_at=NOW + timedelta(hours=2),
        rationale="The rollback lane must be green before replay promotion.",
    )
    request = prepare_replay_request(
        approved,
        approval,
        request_id="replay-rollback-guard",
        repository_uri=bundle.agent_trace.repository_uri,
        commit_sha=bundle.agent_trace.commit_sha,
        baseline_manifest_digest=bundle.experiment_manifest.manifest_digest,
        heldout_split_digest=bundle.experiment_manifest.dataset_split_digest,
        prepared_at=NOW + timedelta(minutes=2),
    )
    assert approved.status == "approved"
    assert request.execution == "external_runner_required"
    assert request.request_digest.startswith("sha256:")


def test_proposer_cannot_self_approve() -> None:
    _, proposal = _proposal()
    with pytest.raises(ValueError, match="cannot self-approve"):
        approve_intervention(
            proposal,
            approval_id="approval-self",
            reviewer_id=proposal.proposer_id,
            decision="approved",
            reviewed_at=NOW,
            rationale="not independent",
        )


def test_rejected_intervention_cannot_prepare_replay() -> None:
    bundle, proposal = _proposal()
    rejected, approval = approve_intervention(
        proposal,
        approval_id="approval-rejected",
        reviewer_id="human-reviewer",
        decision="rejected",
        reviewed_at=NOW,
        rationale="Insufficient rollback evidence.",
    )
    with pytest.raises(ValueError, match="approved intervention"):
        prepare_replay_request(
            rejected,
            approval,
            request_id="replay-rejected",
            repository_uri=bundle.agent_trace.repository_uri,
            commit_sha=bundle.agent_trace.commit_sha,
            baseline_manifest_digest=bundle.experiment_manifest.manifest_digest,
            heldout_split_digest=bundle.experiment_manifest.dataset_split_digest,
            prepared_at=NOW + timedelta(minutes=1),
        )
