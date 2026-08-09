from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from awe_tracegate.contracts import EvaluationPolicy, EvidenceEnvelope, EvidencePackage
from awe_tracegate.evidence import (
    create_evidence_envelope,
    create_evidence_package,
    validate_evidence_envelope,
)

DIGEST = "sha256:" + "a" * 64
REPOSITORY = "https://github.com/example/synthetic-agent"
COMMIT = "b" * 40


def _envelope() -> EvidenceEnvelope:
    policy = EvaluationPolicy()
    return create_evidence_envelope(
        evidence_id="policy",
        artifact_kind="evaluation_policy",
        producer="synthetic.adapter",
        producer_version="1.0.0",
        producer_digest=DIGEST,
        environment_digest=DIGEST,
        provenance_level="asserted",
        repository_uri=REPOSITORY,
        commit_sha=COMMIT,
        captured_at=datetime(2026, 8, 9, tzinfo=UTC),
        payload=policy.model_dump(mode="json"),
    )


def test_validates_strict_adapter_envelope() -> None:
    envelope = _envelope()

    receipt = validate_evidence_envelope(envelope.model_dump(mode="json"))

    assert receipt.status == "valid"
    assert receipt.artifact_kind == "evaluation_policy"
    assert receipt.reasons == ()


def test_conformance_reports_tampered_payload_without_trusting_it() -> None:
    payload = _envelope().model_dump(mode="json")
    payload["payload"]["minimum_trials"] = 999

    receipt = validate_evidence_envelope(payload)

    assert receipt.status == "invalid"
    assert any("payload_digest" in reason for reason in receipt.reasons)


def test_package_binds_one_exact_repository_revision() -> None:
    envelope = _envelope()
    package = create_evidence_package(
        package_id="synthetic_package",
        repository_uri=REPOSITORY,
        commit_sha=COMMIT,
        created_at=datetime(2026, 8, 9, tzinfo=UTC),
        envelopes=(envelope,),
    )

    assert EvidencePackage.model_validate(package.model_dump(mode="json")) == package


def test_package_rejects_envelope_from_another_commit() -> None:
    envelope = _envelope().model_copy(update={"commit_sha": "c" * 40})

    with pytest.raises(ValidationError, match="commit does not match"):
        create_evidence_package(
            package_id="synthetic_package",
            repository_uri=REPOSITORY,
            commit_sha=COMMIT,
            created_at=datetime(2026, 8, 9, tzinfo=UTC),
            envelopes=(envelope,),
        )


def test_envelope_rejects_unknown_fields() -> None:
    payload = _envelope().model_dump(mode="json")
    payload["trusted"] = True

    with pytest.raises(ValidationError, match="Extra inputs"):
        EvidenceEnvelope.model_validate(payload)


def test_non_asserted_provenance_requires_external_verification_receipt() -> None:
    payload = _envelope().model_dump(mode="json")
    payload["provenance_level"] = "attested"

    with pytest.raises(ValidationError, match="external receipt digest"):
        EvidenceEnvelope.model_validate(payload)
