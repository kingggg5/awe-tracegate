"""Provider-neutral evidence envelopes and deterministic conformance checks."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any

from pydantic import ValidationError

from .contracts import (
    PENDING_SHA256_DIGEST,
    AdapterConformanceReceipt,
    EvidenceArtifactKind,
    EvidenceEnvelope,
    EvidencePackage,
    GitCommitSha,
    ProvenanceLevel,
    RepositoryUri,
    Sha256Digest,
    ToolName,
    ToolVersion,
    TraceIdentifier,
    canonical_digest,
)


def _conformance_payload(
    receipt: AdapterConformanceReceipt,
) -> dict[str, object]:
    return receipt.model_dump(mode="json", exclude={"receipt_hash"})


def _validation_reasons(error: ValidationError) -> tuple[str, ...]:
    reasons: set[str] = set()
    for item in error.errors(include_input=False, include_url=False):
        location = ".".join(str(part) for part in item["loc"]) or "$"
        reasons.add(f"invalid:{location}:{item['type']}")
    return tuple(sorted(reasons)) or ("invalid:envelope:validation_error",)


def validate_evidence_envelope(payload: Any) -> AdapterConformanceReceipt:
    """Validate an adapter envelope without executing or trusting its payload."""

    try:
        envelope = EvidenceEnvelope.model_validate(payload)
    except ValidationError as error:
        status = "invalid"
        artifact_kind = None
        reason_set = set(_validation_reasons(error))
        if (
            isinstance(payload, dict)
            and "payload" in payload
            and isinstance(payload.get("payload_digest"), str)
            and canonical_digest(payload["payload"]) != payload["payload_digest"]
        ):
            reason_set.add("invalid:payload_digest:mismatch")
        reasons = tuple(sorted(reason_set))
        envelope_digest = canonical_digest(payload)
    else:
        status = "valid"
        artifact_kind = envelope.artifact_kind
        reasons = ()
        envelope_digest = canonical_digest(envelope)

    receipt = AdapterConformanceReceipt.model_construct(
        schema_version="awe.adapter-conformance.v1",
        status=status,
        envelope_digest=envelope_digest,
        artifact_kind=artifact_kind,
        reasons=reasons,
        receipt_hash=PENDING_SHA256_DIGEST,
    )
    canonical = _conformance_payload(receipt)
    return AdapterConformanceReceipt.model_validate(
        {**canonical, "receipt_hash": canonical_digest(canonical)}
    )


def create_evidence_envelope(
    *,
    evidence_id: TraceIdentifier,
    artifact_kind: EvidenceArtifactKind,
    producer: ToolName,
    producer_version: ToolVersion,
    producer_digest: Sha256Digest,
    environment_digest: Sha256Digest,
    provenance_level: ProvenanceLevel,
    provenance_verification_digest: Sha256Digest | None = None,
    repository_uri: RepositoryUri,
    commit_sha: GitCommitSha,
    captured_at: datetime,
    payload: dict[str, Any],
) -> EvidenceEnvelope:
    """Wrap one already-observed artifact in a content-addressed envelope."""

    return EvidenceEnvelope(
        evidence_id=evidence_id,
        artifact_kind=artifact_kind,
        producer=producer,
        producer_version=producer_version,
        producer_digest=producer_digest,
        environment_digest=environment_digest,
        provenance_level=provenance_level,
        provenance_verification_digest=provenance_verification_digest,
        repository_uri=repository_uri,
        commit_sha=commit_sha,
        captured_at=captured_at,
        payload=payload,
        payload_digest=canonical_digest(payload),
    )


def create_evidence_package(
    *,
    package_id: TraceIdentifier,
    repository_uri: RepositoryUri,
    commit_sha: GitCommitSha,
    created_at: datetime,
    envelopes: Sequence[EvidenceEnvelope],
) -> EvidencePackage:
    """Create a deterministic package after enforcing one repository revision."""

    ordered = tuple(sorted(envelopes, key=lambda item: item.evidence_id))
    package = EvidencePackage.model_construct(
        schema_version="awe.evidence-package.v1",
        package_id=package_id,
        repository_uri=repository_uri,
        commit_sha=commit_sha,
        created_at=created_at,
        envelopes=ordered,
        package_digest=PENDING_SHA256_DIGEST,
    )
    payload = package.model_dump(mode="json", exclude={"package_digest"})
    return EvidencePackage.model_validate(
        {**payload, "package_digest": canonical_digest(payload)}
    )
