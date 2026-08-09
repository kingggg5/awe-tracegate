from __future__ import annotations

import hashlib
import io
import json
import tarfile
import zipfile
from pathlib import Path

from awe_tracegate.cli import main as cli_main
from scripts.build_release_bundles import (
    FIXED_ZIP_TIMESTAMP,
    build_plugin_bundle,
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
        assert ".codex-plugin/plugin.json" in names
        assert any(name.endswith("/SKILL.md") for name in names)
        assert all(item.date_time == FIXED_ZIP_TIMESTAMP for item in archive.infolist())


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
