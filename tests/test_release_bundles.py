from __future__ import annotations

import hashlib
import io
import json
import shutil
import tarfile
import zipfile
from pathlib import Path

import pytest

from awe_tracegate.cli import main as cli_main
from scripts.build_release_bundles import (
    FIXED_ZIP_TIMESTAMP,
    build_plugin_bundle,
    build_schema_bundle,
    release_versions,
    verify_release_version,
    write_gate_predicate,
    write_release_metadata,
)

ROOT = Path(__file__).parents[1]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _gate_receipt(tmp_path: Path) -> Path:
    receipt = tmp_path / "gate.json"
    assert (
        cli_main(
            [
                "gate",
                "--traces",
                str(ROOT / "examples/repo_analysis/traces.jsonl"),
                "--baseline",
                str(ROOT / "examples/evaluation/baseline.json"),
                "--candidate",
                str(ROOT / "examples/evaluation/candidate.json"),
                "--policy",
                str(ROOT / "examples/evaluation/policy.json"),
                "--out",
                str(receipt),
            ]
        )
        == 0
    )
    return receipt


def test_plugin_bundle_is_byte_reproducible(tmp_path: Path) -> None:
    first = tmp_path / "first.zip"
    second = tmp_path / "second.zip"

    assert build_plugin_bundle(ROOT, first) == build_plugin_bundle(ROOT, second)
    assert first.read_bytes() == second.read_bytes()

    with zipfile.ZipFile(first) as archive:
        names = archive.namelist()
        assert names == sorted(names)
        assert "LICENSE" in names
        assert ".codex-plugin/plugin.json" in names
        assert ".claude-plugin/marketplace.json" in names
        assert "integrations/claude-code/.claude-plugin/plugin.json" in names
        assert any(name.endswith("/SKILL.md") for name in names)
        assert all(item.date_time == FIXED_ZIP_TIMESTAMP for item in archive.infolist())


def test_schema_bundle_is_byte_reproducible(tmp_path: Path) -> None:
    schemas = tmp_path / "schemas"
    nested = schemas / "nested"
    nested.mkdir(parents=True)
    (schemas / "z.json").write_text('{"title":"Z"}\n', encoding="utf-8")
    (nested / "a.json").write_text('{"title":"A"}\n', encoding="utf-8")
    first = tmp_path / "first.zip"
    second = tmp_path / "second.zip"

    assert build_schema_bundle(schemas, first) == build_schema_bundle(schemas, second)
    assert first.read_bytes() == second.read_bytes()
    with zipfile.ZipFile(first) as archive:
        assert archive.namelist() == ["nested/a.json", "z.json"]
        assert all(item.date_time == FIXED_ZIP_TIMESTAMP for item in archive.infolist())


def _copy_version_surface(target: Path) -> None:
    files = (
        "pyproject.toml",
        "package.json",
        "package-lock.json",
        ".codex-plugin/plugin.json",
        ".claude-plugin/marketplace.json",
        "integrations/claude-code/.claude-plugin/plugin.json",
        "sdk/typescript/package.json",
        "sdk/typescript/package-lock.json",
        "src/awe_tracegate/__init__.py",
        "scripts/install_skills.py",
    )
    for relative in files:
        source = ROOT / relative
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)


def test_release_version_matches_every_distribution_and_semver_tag(
    tmp_path: Path,
) -> None:
    _copy_version_surface(tmp_path)

    versions = release_versions(tmp_path)
    assert set(versions.values()) == {"0.3.0"}
    assert verify_release_version(tmp_path, "v0.3.0") == "0.3.0"


def test_release_version_rejects_tag_or_manifest_drift(tmp_path: Path) -> None:
    _copy_version_surface(tmp_path)

    with pytest.raises(ValueError, match="must equal"):
        verify_release_version(tmp_path, "v0.3.1")

    package = json.loads((tmp_path / "package.json").read_text(encoding="utf-8"))
    package["version"] = "0.3.1"
    (tmp_path / "package.json").write_text(json.dumps(package) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="versions do not match"):
        verify_release_version(tmp_path, "v0.3.0")


def test_release_workflow_assembles_and_smokes_complete_artifact_set() -> None:
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(
        encoding="utf-8"
    )
    continuous_integration = (ROOT / ".github" / "workflows" / "ci.yml").read_text(
        encoding="utf-8"
    )

    assert 'tags: ["v*"]' in workflow
    assert "workflow_call:" in continuous_integration
    assert "verify-tagged-source:" in workflow
    assert "uses: ./.github/workflows/ci.yml" in workflow
    assert "needs: verify-tagged-source" in workflow
    assert "permissions:\n  contents: read" in workflow
    assert "contents: write" in workflow
    assert workflow.index("needs: verify-tagged-source") < workflow.index(
        "contents: write"
    )
    assert "build_release_bundles.py version" in workflow
    assert "python -m build --outdir dist" in workflow
    assert "npm pack --pack-destination dist" in workflow
    assert "dist/awe-tracegate-plugin.zip" in workflow
    assert "dist/awe-tracegate-schemas.zip" in workflow
    assert "dist/awe-tracegate-release.spdx.json" in workflow
    assert "--checksums dist/SHA256SUMS" in workflow
    assert "sha256sum --check SHA256SUMS" in workflow
    assert '"${RUNNER_TEMP}/python-smoke/bin/awe" gate' in workflow
    assert '"${cli}" check --target "${target_root}"' in workflow
    assert '"${cli}" --version' in workflow
    assert "subject-path: dist/*" in workflow
    assert "git tag" not in workflow
    assert "git push" not in workflow


def test_release_metadata_is_deterministic_and_hashes_every_subject(
    tmp_path: Path,
) -> None:
    dist = tmp_path / "dist"
    dist.mkdir()
    npm_version = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))[
        "version"
    ]
    npm_archive = f"awe-tracegate-{npm_version}.tgz"
    build_plugin_bundle(ROOT, dist / "awe-tracegate-plugin.zip")
    package_json = b'{"name":"awe-tracegate"}'
    with tarfile.open(dist / npm_archive, mode="w:gz") as archive:
        info = tarfile.TarInfo("package/package.json")
        info.mtime = 0
        info.size = len(package_json)
        archive.addfile(info, io.BytesIO(package_json))
    sbom = dist / "awe-tracegate-release.spdx.json"
    checksums = dist / "SHA256SUMS"

    write_release_metadata(ROOT, dist, sbom, checksums, source_date_epoch=0)
    first_sbom = sbom.read_bytes()
    first_checksums = checksums.read_bytes()
    write_release_metadata(ROOT, dist, sbom, checksums, source_date_epoch=0)

    assert sbom.read_bytes() == first_sbom
    assert checksums.read_bytes() == first_checksums
    document = json.loads(first_sbom)
    assert document["spdxVersion"] == "SPDX-2.3"
    described = {
        package["name"]
        for package in document["packages"]
        if package.get("primaryPackagePurpose") == "FILE"
    }
    assert described == {npm_archive, "awe-tracegate-plugin.zip"}
    inventoried_files = {item["fileName"] for item in document["files"]}
    assert f"./{npm_archive}!/package/package.json" in inventoried_files
    assert "./awe-tracegate-plugin.zip!/.codex-plugin/plugin.json" in inventoried_files
    assert (
        "./awe-tracegate-plugin.zip!/integrations/claude-code/"
        ".claude-plugin/plugin.json"
    ) in inventoried_files

    lines = checksums.read_text(encoding="utf-8").splitlines()
    names = [line.split(" *", maxsplit=1)[1] for line in lines]
    assert names == sorted(names)
    assert names == [
        npm_archive,
        "awe-tracegate-plugin.zip",
        "awe-tracegate-release.spdx.json",
    ]
    for line in lines:
        digest, name = line.split(" *", maxsplit=1)
        assert digest == _sha256(dist / name)


def test_gate_predicate_binds_subject_commit_and_raw_inputs(tmp_path: Path) -> None:
    receipt = _gate_receipt(tmp_path)
    candidate = ROOT / "examples/evaluation/candidate.json"
    output = tmp_path / "predicate.json"
    evidence = (
        ("execution_traces", ROOT / "examples/repo_analysis/traces.jsonl"),
        ("baseline_evaluation", ROOT / "examples/evaluation/baseline.json"),
        ("candidate_evaluation", candidate),
        ("evaluation_policy", ROOT / "examples/evaluation/policy.json"),
    )

    write_gate_predicate(
        receipt,
        candidate,
        evidence,
        "https://github.com/kingggg5/awe-tracegate",
        "a" * 40,
        output,
    )

    predicate = json.loads(output.read_text(encoding="utf-8"))
    assert predicate["schema_version"] == ("awe.github-gate-attestation-predicate.v1")
    assert predicate["gate_receipt"]["status"] == "PASS"
    assert predicate["commit_sha"] == "a" * 40
    assert predicate["subject"] == {
        "name": "candidate.json",
        "sha256": f"sha256:{_sha256(candidate)}",
    }
    assert len(predicate["evidence"]) == 4
