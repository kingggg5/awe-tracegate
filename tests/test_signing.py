from __future__ import annotations

from datetime import UTC, datetime

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pydantic import ValidationError

from awe_tracegate.contracts import SignedReceiptBundle
from awe_tracegate.signing import create_signed_bundle, verify_signed_bundle

REPOSITORY = "https://github.com/example/agent"
COMMIT = "a" * 40
SIGNER = "maintainer@example.com"


def keys() -> tuple[bytes, bytes]:
    private_key = Ed25519PrivateKey.generate()
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    return private_pem, public_pem


def bundle(private_pem: bytes) -> SignedReceiptBundle:
    return create_signed_bundle(
        {"schema_version": "example.v1", "status": "pass"},
        artifact_kind="evaluation",
        repository_uri=REPOSITORY,
        commit_sha=COMMIT,
        signer_id=SIGNER,
        issued_at=datetime(2026, 8, 9, tzinfo=UTC),
        private_key_pem=private_pem,
    )


def test_verifies_against_explicit_trust_policy() -> None:
    private_pem, public_pem = keys()
    signed = bundle(private_pem)

    result = verify_signed_bundle(
        signed,
        trusted_public_key_pem=public_pem,
        expected_signer_id=SIGNER,
        expected_repository_uri=REPOSITORY,
        expected_commit_sha=COMMIT,
    )

    assert result.status == "valid"
    assert result.reasons == ()
    assert result.verification_hash.startswith("sha256:")


def test_signature_does_not_override_repository_or_commit_policy() -> None:
    private_pem, public_pem = keys()
    signed = bundle(private_pem)

    result = verify_signed_bundle(
        signed,
        trusted_public_key_pem=public_pem,
        expected_signer_id=SIGNER,
        expected_repository_uri="https://github.com/example/other",
        expected_commit_sha="b" * 40,
    )

    assert result.status == "invalid"
    assert result.reasons == ("commit_sha_mismatch", "repository_mismatch")


def test_rejects_artifact_tampering_before_signature_verification() -> None:
    private_pem, _ = keys()
    payload = bundle(private_pem).model_dump(mode="json")
    payload["artifact"]["status"] = "block"

    with pytest.raises(ValidationError, match="signed artifact digest"):
        SignedReceiptBundle.model_validate(payload)


def test_detects_signature_tampering() -> None:
    private_pem, public_pem = keys()
    payload = bundle(private_pem).model_dump(mode="json")
    original = payload["signature_b64"]
    payload["signature_b64"] = ("B" if original[0] != "B" else "C") + original[1:]
    signed = SignedReceiptBundle.model_validate(payload)

    result = verify_signed_bundle(
        signed,
        trusted_public_key_pem=public_pem,
        expected_signer_id=SIGNER,
        expected_repository_uri=REPOSITORY,
        expected_commit_sha=COMMIT,
    )

    assert result.status == "invalid"
    assert result.reasons == ("invalid_signature",)


def test_rejects_untrusted_key() -> None:
    private_pem, _ = keys()
    _, other_public_pem = keys()

    result = verify_signed_bundle(
        bundle(private_pem),
        trusted_public_key_pem=other_public_pem,
        expected_signer_id=SIGNER,
        expected_repository_uri=REPOSITORY,
        expected_commit_sha=COMMIT,
    )

    assert result.status == "invalid"
    assert result.reasons == ("invalid_signature", "untrusted_public_key")
