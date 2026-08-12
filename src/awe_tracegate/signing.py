"""Optional Ed25519 signing for repository- and commit-bound receipt bundles."""

from __future__ import annotations

import base64
from datetime import datetime
from typing import Any, Literal

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from pydantic import BaseModel

from .contracts import (
    PENDING_SHA256_DIGEST,
    GitCommitSha,
    RepositoryUri,
    SignatureVerification,
    SignedReceiptBundle,
    SignerIdentity,
    canonical_digest,
    canonical_json,
)

ArtifactKind = Literal[
    "compilation",
    "verification",
    "evaluation",
    "experiment",
    "promotion",
    "evidence_package",
]


def _artifact_payload(artifact: BaseModel | dict[str, Any]) -> dict[str, Any]:
    payload = (
        artifact.model_dump(mode="json", exclude_none=False)
        if isinstance(artifact, BaseModel)
        else artifact
    )
    if not isinstance(payload, dict):
        raise ValueError("signed artifact must be a JSON object")
    canonical_json(payload)
    return payload


def _signature_payload(bundle: SignedReceiptBundle) -> dict[str, Any]:
    return bundle.model_dump(mode="json", exclude={"signature_b64"})


def _raw_public_key(public_key: Ed25519PublicKey) -> bytes:
    return public_key.public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )


def _public_key_fingerprint(raw_public_key: bytes) -> str:
    return canonical_digest(
        {
            "algorithm": "ed25519",
            "public_key_b64": base64.b64encode(raw_public_key).decode("ascii"),
        }
    )


def _load_private_key(pem: bytes, password: bytes | None) -> Ed25519PrivateKey:
    key = serialization.load_pem_private_key(pem, password=password)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError("private key must use Ed25519")
    return key


def _load_public_key(pem: bytes) -> Ed25519PublicKey:
    key = serialization.load_pem_public_key(pem)
    if not isinstance(key, Ed25519PublicKey):
        raise ValueError("trusted public key must use Ed25519")
    return key


def create_signed_bundle(
    artifact: BaseModel | dict[str, Any],
    *,
    artifact_kind: ArtifactKind,
    repository_uri: RepositoryUri,
    commit_sha: GitCommitSha,
    signer_id: SignerIdentity,
    issued_at: datetime,
    private_key_pem: bytes,
    private_key_password: bytes | None = None,
) -> SignedReceiptBundle:
    """Sign canonical bundle bytes; the caller owns key custody and identity policy."""

    artifact_payload = _artifact_payload(artifact)
    private_key = _load_private_key(private_key_pem, private_key_password)
    raw_public_key = _raw_public_key(private_key.public_key())
    unsigned = SignedReceiptBundle.model_construct(
        artifact_kind=artifact_kind,
        artifact_digest=canonical_digest(artifact_payload),
        artifact=artifact_payload,
        repository_uri=repository_uri,
        commit_sha=commit_sha,
        signer_id=signer_id,
        issued_at=issued_at,
        public_key_b64=base64.b64encode(raw_public_key).decode("ascii"),
        public_key_fingerprint=_public_key_fingerprint(raw_public_key),
        signature_b64="A" * 86 + "==",
    )
    signature = private_key.sign(
        canonical_json(_signature_payload(unsigned)).encode("utf-8")
    )
    return SignedReceiptBundle.model_validate(
        {
            **_signature_payload(unsigned),
            "signature_b64": base64.b64encode(signature).decode("ascii"),
        }
    )


def verify_signed_bundle(
    bundle: SignedReceiptBundle,
    *,
    trusted_public_key_pem: bytes,
    expected_signer_id: SignerIdentity,
    expected_repository_uri: RepositoryUri,
    expected_commit_sha: GitCommitSha,
) -> SignatureVerification:
    """Verify signature plus explicit key, signer, repository, and commit policy."""

    reasons: list[str] = []
    trusted_key = _load_public_key(trusted_public_key_pem)
    trusted_raw = _raw_public_key(trusted_key)
    embedded_raw = base64.b64decode(bundle.public_key_b64, validate=True)
    trusted_fingerprint = _public_key_fingerprint(trusted_raw)
    if (
        embedded_raw != trusted_raw
        or bundle.public_key_fingerprint != trusted_fingerprint
    ):
        reasons.append("untrusted_public_key")
    if bundle.signer_id != expected_signer_id:
        reasons.append("signer_identity_mismatch")
    if bundle.repository_uri != expected_repository_uri:
        reasons.append("repository_mismatch")
    if bundle.commit_sha != expected_commit_sha:
        reasons.append("commit_sha_mismatch")
    try:
        trusted_key.verify(
            base64.b64decode(bundle.signature_b64, validate=True),
            canonical_json(_signature_payload(bundle)).encode("utf-8"),
        )
    except (InvalidSignature, ValueError):
        reasons.append("invalid_signature")

    provisional = SignatureVerification.model_construct(
        status="invalid" if reasons else "valid",
        bundle_digest=canonical_digest(bundle),
        artifact_kind=bundle.artifact_kind,
        artifact_digest=bundle.artifact_digest,
        signer_id=bundle.signer_id,
        public_key_fingerprint=bundle.public_key_fingerprint,
        reasons=tuple(sorted(set(reasons))),
        verification_hash=PENDING_SHA256_DIGEST,
    )
    payload = provisional.model_dump(mode="json", exclude={"verification_hash"})
    return SignatureVerification.model_validate(
        {**payload, "verification_hash": canonical_digest(payload)}
    )
