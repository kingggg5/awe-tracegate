from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from pydantic import ValidationError

from awe_tracegate.contracts import (
    PENDING_SHA256_DIGEST,
    EvaluationBundle,
    EvaluationPolicy,
    ExecutionTrace,
    GateReceipt,
    SkillBom,
    SkillFile,
    canonical_digest,
)
from awe_tracegate.evidence import create_evidence_envelope, create_evidence_package
from awe_tracegate.gate import gate_evidence

ROOT = Path(__file__).parents[1]
REPOSITORY = "https://github.com/example/synthetic-agent"
COMMIT = "a" * 40
DIGEST = "sha256:" + "e" * 64


def _traces() -> tuple[ExecutionTrace, ...]:
    path = ROOT / "examples/repo_analysis/traces.jsonl"
    return tuple(
        ExecutionTrace.model_validate_json(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    )


def _model(name: str, model: type[EvaluationBundle]) -> EvaluationBundle:
    path = ROOT / f"examples/evaluation/{name}.json"
    return model.model_validate_json(path.read_text(encoding="utf-8"))


def _policy() -> EvaluationPolicy:
    path = ROOT / "examples/evaluation/policy.json"
    return EvaluationPolicy.model_validate_json(path.read_text(encoding="utf-8"))


def _skill_bom() -> SkillBom:
    skill_file = SkillFile(
        path="SKILL.md",
        digest=DIGEST,
        size_bytes=128,
        role="instructions",
    )
    skill_digest = canonical_digest([skill_file.model_dump(mode="json")])
    bom = SkillBom.model_construct(
        schema_version="awe.skill-bom.v1",
        skill_name="synthetic-review",
        files=(skill_file,),
        external_urls=(),
        skill_digest=skill_digest,
        bom_digest=PENDING_SHA256_DIGEST,
    )
    payload = bom.model_dump(mode="json", exclude={"bom_digest"})
    return SkillBom.model_validate({**payload, "bom_digest": canonical_digest(payload)})


def _package(
    provenance: str = "attested",
    *,
    age_days: int = 0,
    skill_bom: SkillBom | None = None,
):
    traces = _traces()
    baseline = _model("baseline", EvaluationBundle)
    candidate = _model("candidate", EvaluationBundle)
    policy = _policy()
    captured_at = datetime(2026, 8, 9, tzinfo=UTC) - timedelta(days=age_days)
    inputs = [
        (
            "traces",
            "execution_traces",
            {
                "traces": [
                    trace.model_dump(mode="json")
                    for trace in sorted(traces, key=lambda item: item.trace_id)
                ]
            },
        ),
        ("baseline", "evaluation_bundle", baseline.model_dump(mode="json")),
        ("candidate", "evaluation_bundle", candidate.model_dump(mode="json")),
        ("policy", "evaluation_policy", policy.model_dump(mode="json")),
    ]
    if skill_bom is not None:
        inputs.append(("skill", "skill_bom", skill_bom.model_dump(mode="json")))
    envelopes = tuple(
        create_evidence_envelope(
            evidence_id=evidence_id,
            artifact_kind=artifact_kind,
            producer="synthetic.harness",
            producer_version="1.0.0",
            producer_digest=DIGEST,
            environment_digest=DIGEST,
            provenance_level=provenance,
            provenance_verification_digest=(
                None if provenance == "asserted" else DIGEST
            ),
            repository_uri=REPOSITORY,
            commit_sha=COMMIT,
            captured_at=captured_at,
            payload=payload,
        )
        for evidence_id, artifact_kind, payload in inputs
    )
    package = create_evidence_package(
        package_id="synthetic_gate_inputs",
        repository_uri=REPOSITORY,
        commit_sha=COMMIT,
        created_at=captured_at,
        envelopes=envelopes,
    )
    return traces, baseline, candidate, policy, package


def test_atomic_gate_passes_only_exact_linked_evidence() -> None:
    receipt = gate_evidence(
        _traces(),
        _model("baseline", EvaluationBundle),
        _model("candidate", EvaluationBundle),
        _policy(),
    )

    assert receipt.status == "PASS"
    assert receipt.verification.status == "valid"
    assert receipt.verification.traces_verified is True
    assert receipt.candidate_digest == receipt.evaluation.candidate_digest
    assert receipt.receipt_hash == (
        "sha256:20846ba82b0d81a8946989e3e55c28a9899033154cf7e8ab5b1d358992572638"
    )
    assert GateReceipt.model_validate(receipt.model_dump(mode="json")) == receipt


def test_atomic_gate_blocks_evaluation_for_another_candidate() -> None:
    candidate = _model("candidate", EvaluationBundle).model_copy(
        update={"subject_digest": "sha256:" + "f" * 64}
    )

    receipt = gate_evidence(
        _traces(), _model("baseline", EvaluationBundle), candidate, _policy()
    )

    assert receipt.status == "BLOCK"
    assert "evaluation:candidate_digest_mismatch" in receipt.reasons


def test_atomic_gate_reviews_insufficient_frozen_trials() -> None:
    baseline = _model("baseline", EvaluationBundle)
    candidate = _model("candidate", EvaluationBundle)
    baseline = baseline.model_copy(update={"trials": baseline.trials[:1]})
    candidate = candidate.model_copy(update={"trials": candidate.trials[:1]})

    receipt = gate_evidence(_traces(), baseline, candidate, _policy())

    assert receipt.status == "REVIEW"
    assert receipt.reasons == ("evaluation:insufficient_trials",)


def test_atomic_gate_blocks_without_enough_trace_evidence() -> None:
    receipt = gate_evidence(
        _traces()[:1],
        _model("baseline", EvaluationBundle),
        _model("candidate", EvaluationBundle),
        _policy(),
    )

    assert receipt.status == "BLOCK"
    assert "compilation:insufficient_trace_evidence" in receipt.reasons
    assert receipt.verification.traces_verified is True


def test_gate_rejects_unverified_external_provenance_floor() -> None:
    traces, baseline, candidate, policy, package = _package("asserted")

    with pytest.raises(ValueError, match="only asserted provenance"):
        gate_evidence(
            traces,
            baseline,
            candidate,
            policy,
            evidence_package=package,
            expected_repository=REPOSITORY,
            expected_commit_sha=COMMIT,
            minimum_provenance_level="attested",
        )


def test_gate_accepts_fresh_exact_package_with_asserted_floor() -> None:
    traces, baseline, candidate, policy, package = _package("asserted")

    receipt = gate_evidence(
        traces,
        baseline,
        candidate,
        policy,
        evidence_package=package,
        expected_repository=REPOSITORY,
        expected_commit_sha=COMMIT,
        evaluated_at=datetime(2026, 8, 9, 0, 5, tzinfo=UTC),
        maximum_age_seconds=600,
        minimum_provenance_level="asserted",
    )

    assert receipt.status == "PASS"
    assert receipt.evidence_package_digest == package.package_digest
    assert receipt.repository_uri == REPOSITORY
    assert receipt.commit_sha == COMMIT


def test_gate_receipt_cannot_claim_pass_from_unverified_provenance() -> None:
    traces, baseline, candidate, policy, package = _package("asserted")
    receipt = gate_evidence(
        traces,
        baseline,
        candidate,
        policy,
        evidence_package=package,
        minimum_provenance_level="asserted",
    )
    forged = receipt.model_dump(mode="json")
    forged["evidence_provenance_level"] = "attested"
    forged["minimum_provenance_level"] = "attested"
    forged["receipt_hash"] = canonical_digest(
        {key: value for key, value in forged.items() if key != "receipt_hash"}
    )

    with pytest.raises(ValidationError, match="unverified external provenance"):
        GateReceipt.model_validate(forged)


def test_gate_binds_skill_bom_without_changing_behavior_candidate() -> None:
    bom = _skill_bom()
    without_bom = gate_evidence(
        _traces(),
        _model("baseline", EvaluationBundle),
        _model("candidate", EvaluationBundle),
        _policy(),
    )
    with_bom = gate_evidence(
        _traces(),
        _model("baseline", EvaluationBundle),
        _model("candidate", EvaluationBundle),
        _policy(),
        skill_bom=bom,
    )

    assert with_bom.status == "PASS"
    assert with_bom.skill_bom_digest == bom.bom_digest
    assert with_bom.candidate_digest == without_bom.candidate_digest
    assert with_bom.receipt_hash != without_bom.receipt_hash


def test_gate_requires_matching_skill_bom_in_evidence_package() -> None:
    bom = _skill_bom()
    traces, baseline, candidate, policy, package = _package()

    missing = gate_evidence(
        traces,
        baseline,
        candidate,
        policy,
        evidence_package=package,
        skill_bom=bom,
    )
    assert missing.status == "BLOCK"
    assert "evidence_package_missing_gate_inputs" in missing.reasons

    traces, baseline, candidate, policy, matching_package = _package(skill_bom=bom)
    matching = gate_evidence(
        traces,
        baseline,
        candidate,
        policy,
        evidence_package=matching_package,
        skill_bom=bom,
    )
    assert matching.status == "PASS"
    assert matching.skill_bom_digest == bom.bom_digest


def test_gate_blocks_expired_package() -> None:
    traces, baseline, candidate, policy, package = _package(age_days=2)

    receipt = gate_evidence(
        traces,
        baseline,
        candidate,
        policy,
        evidence_package=package,
        evaluated_at=datetime(2026, 8, 9, tzinfo=UTC),
        maximum_age_seconds=86_400,
    )

    assert receipt.status == "BLOCK"
    assert "evidence_package_expired" in receipt.reasons


def test_gate_receipt_rejects_tampered_nested_evaluation() -> None:
    receipt = gate_evidence(
        _traces(),
        _model("baseline", EvaluationBundle),
        _model("candidate", EvaluationBundle),
        _policy(),
    )
    tampered = receipt.model_dump(mode="json")
    tampered["evaluation"]["candidate"]["success_count"] = 0

    with pytest.raises(ValidationError, match="evaluation receipt hash"):
        GateReceipt.model_validate(tampered)


def test_gate_receipt_rejects_tampered_skill_bom_binding() -> None:
    receipt = gate_evidence(
        _traces(),
        _model("baseline", EvaluationBundle),
        _model("candidate", EvaluationBundle),
        _policy(),
        skill_bom=_skill_bom(),
    )
    tampered = receipt.model_dump(mode="json")
    tampered["skill_bom_digest"] = "sha256:" + "f" * 64

    with pytest.raises(ValidationError, match="gate receipt hash"):
        GateReceipt.model_validate(tampered)
