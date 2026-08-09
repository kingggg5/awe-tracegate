"""Build reproducible plugin bundles and release supply-chain metadata."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import tarfile
import tomllib
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

FIXED_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
IGNORED_NAMES = {".DS_Store", "Thumbs.db"}
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
MAX_ARCHIVE_FILES = 10_000
MAX_ARCHIVE_BYTES = 256 * 1024 * 1024


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, allow_nan=False, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _plugin_files(root: Path) -> tuple[Path, ...]:
    claude_root = root / "integrations" / "claude-code"
    if claude_root.is_symlink():
        raise ValueError(f"plugin bundle refuses symbolic link: {claude_root}")
    required = (
        root / ".codex-plugin" / "plugin.json",
        root / ".claude-plugin" / "marketplace.json",
        claude_root / ".claude-plugin" / "plugin.json",
    )
    missing = [
        path.relative_to(root).as_posix() for path in required if not path.is_file()
    ]
    if missing:
        raise ValueError(f"plugin bundle requires: {', '.join(missing)}")

    candidates = list(required)
    marketplace = root / ".agents" / "plugins" / "marketplace.json"
    if marketplace.is_file():
        candidates.append(marketplace)
    candidates.extend((root / "skills").rglob("*"))
    candidates.extend((claude_root / "skills").rglob("*"))

    files: list[Path] = []
    for path in candidates:
        if path.name in IGNORED_NAMES or "__pycache__" in path.parts:
            continue
        if path.is_symlink():
            raise ValueError(f"plugin bundle refuses symbolic link: {path}")
        if path.is_file():
            files.append(path)
    if not any(path.name == "SKILL.md" for path in files):
        raise ValueError("plugin bundle requires at least one SKILL.md")
    return tuple(sorted(set(files), key=lambda item: item.relative_to(root).as_posix()))


def build_plugin_bundle(root: Path, output: Path) -> str:
    root = root.resolve(strict=True)
    files = _plugin_files(root)
    if output.is_symlink():
        raise ValueError(f"plugin output must not be a symbolic link: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_STORED) as archive:
        for path in files:
            relative = path.relative_to(root).as_posix()
            info = zipfile.ZipInfo(relative, date_time=FIXED_ZIP_TIMESTAMP)
            info.create_system = 3
            info.external_attr = (0o100644 & 0xFFFF) << 16
            archive.writestr(info, path.read_bytes())
    return _sha256(output)


def _archive_members(path: Path) -> tuple[tuple[str, bytes], ...]:
    members: list[tuple[str, bytes]] = []
    total_bytes = 0
    if path.suffix in {".zip", ".whl"}:
        with zipfile.ZipFile(path) as archive:
            for info in sorted(archive.infolist(), key=lambda item: item.filename):
                if info.is_dir():
                    continue
                mode = (info.external_attr >> 16) & 0o170000
                if mode == 0o120000:
                    raise ValueError(f"release archive contains a symlink: {path}")
                payload = archive.read(info)
                members.append((info.filename, payload))
                total_bytes += len(payload)
    elif path.name.endswith((".tgz", ".tar.gz")):
        with tarfile.open(path, mode="r:gz") as archive:
            for info in sorted(archive.getmembers(), key=lambda item: item.name):
                if info.issym() or info.islnk():
                    raise ValueError(f"release archive contains a link: {path}")
                if not info.isfile():
                    continue
                stream = archive.extractfile(info)
                if stream is None:
                    raise ValueError(
                        f"release archive member is unreadable: {info.name}"
                    )
                payload = stream.read()
                members.append((info.name, payload))
                total_bytes += len(payload)
    if len(members) > MAX_ARCHIVE_FILES or total_bytes > MAX_ARCHIVE_BYTES:
        raise ValueError(f"release archive exceeds the SBOM inventory limit: {path}")
    return tuple(members)


def _archive_file_records(
    artifact: Path, artifact_spdx_id: str
) -> tuple[list[dict[str, Any]], list[dict[str, str]]]:
    files: list[dict[str, Any]] = []
    relationships: list[dict[str, str]] = []
    for name, payload in _archive_members(artifact):
        digest = hashlib.sha256(payload).hexdigest()
        identity = hashlib.sha256(f"{artifact.name}!/{name}".encode()).hexdigest()
        spdx_id = f"SPDXRef-File-{identity[:24]}"
        files.append(
            {
                "SPDXID": spdx_id,
                "checksums": [{"algorithm": "SHA256", "checksumValue": digest}],
                "copyrightText": "NOASSERTION",
                "fileName": f"./{artifact.name}!/{name}",
                "licenseConcluded": "NOASSERTION",
            }
        )
        relationships.append(
            {
                "relatedSpdxElement": spdx_id,
                "relationshipType": "CONTAINS",
                "spdxElementId": artifact_spdx_id,
            }
        )
    return files, relationships


def _artifact_packages(
    dist: Path, versions: dict[str, str]
) -> tuple[list[dict[str, Any]], list[dict[str, str]], list[dict[str, Any]]]:
    packages: list[dict[str, Any]] = []
    relationships: list[dict[str, str]] = []
    files: list[dict[str, Any]] = []
    for path in sorted(dist.iterdir(), key=lambda item: item.name):
        if path.is_symlink():
            raise ValueError(f"release metadata refuses symbolic link: {path}")
        if not path.is_file() or path.name in {"SHA256SUMS"}:
            continue
        if path.name.endswith((".spdx.json", ".predicate.json")):
            continue
        digest = _sha256(path)
        spdx_id = f"SPDXRef-Artifact-{digest[:24]}"
        version = versions["project"]
        if path.name == "awe-tracegate-plugin.zip":
            version = versions["plugin"]
        elif path.name.endswith(".tgz") and path.name.startswith("awe-tracegate-"):
            version = versions["npm"]
        packages.append(
            {
                "SPDXID": spdx_id,
                "checksums": [{"algorithm": "SHA256", "checksumValue": digest}],
                "copyrightText": "NOASSERTION",
                "downloadLocation": "NOASSERTION",
                "filesAnalyzed": False,
                "licenseConcluded": "NOASSERTION",
                "licenseDeclared": "Apache-2.0",
                "name": path.name,
                "primaryPackagePurpose": "FILE",
                "versionInfo": version,
            }
        )
        relationships.append(
            {
                "relatedSpdxElement": spdx_id,
                "relationshipType": "DESCRIBES",
                "spdxElementId": "SPDXRef-DOCUMENT",
            }
        )
        member_files, member_relationships = _archive_file_records(path, spdx_id)
        files.extend(member_files)
        relationships.extend(member_relationships)
    if not packages:
        raise ValueError(f"no release artifacts found in {dist}")
    return packages, relationships, files


def _npm_dependencies(lockfile: Path) -> list[dict[str, Any]]:
    if not lockfile.is_file():
        return []
    payload = json.loads(lockfile.read_text(encoding="utf-8"))
    packages = payload.get("packages")
    if not isinstance(packages, dict):
        raise ValueError(f"{lockfile} does not contain npm lockfile packages")

    dependencies: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for location, metadata in sorted(packages.items()):
        if (
            not location
            or not isinstance(metadata, dict)
            or metadata.get("dev") is True
        ):
            continue
        name = metadata.get("name")
        version = metadata.get("version")
        if not isinstance(name, str):
            name = location.rsplit("node_modules/", maxsplit=1)[-1]
        if not isinstance(version, str) or (name, version) in seen:
            continue
        seen.add((name, version))
        identity = hashlib.sha256(f"{name}@{version}".encode()).hexdigest()[:24]
        if name.startswith("@") and "/" in name:
            scope, package = name[1:].split("/", maxsplit=1)
            purl_name = f"%40{quote(scope, safe='')}/{quote(package, safe='')}"
        else:
            purl_name = quote(name, safe="")
        dependencies.append(
            {
                "SPDXID": f"SPDXRef-Npm-{identity}",
                "copyrightText": "NOASSERTION",
                "downloadLocation": "NOASSERTION",
                "externalRefs": [
                    {
                        "referenceCategory": "PACKAGE-MANAGER",
                        "referenceLocator": f"pkg:npm/{purl_name}@{version}",
                        "referenceType": "purl",
                    }
                ],
                "filesAnalyzed": False,
                "licenseConcluded": "NOASSERTION",
                "licenseDeclared": "NOASSERTION",
                "name": name,
                "primaryPackagePurpose": "LIBRARY",
                "versionInfo": version,
            }
        )
    return dependencies


def write_release_metadata(
    root: Path,
    dist: Path,
    sbom_path: Path,
    checksums_path: Path,
    source_date_epoch: int,
) -> None:
    root = root.resolve(strict=True)
    dist = dist.resolve(strict=True)
    for label, path in (("SBOM", sbom_path), ("checksums", checksums_path)):
        if path.resolve().parent != dist:
            raise ValueError(f"{label} output must be directly inside {dist}")
        if path.is_symlink():
            raise ValueError(f"{label} output must not be a symbolic link: {path}")
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    plugin = json.loads(
        (root / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    claude_plugin = json.loads(
        (
            root / "integrations" / "claude-code" / ".claude-plugin" / "plugin.json"
        ).read_text(encoding="utf-8")
    )
    if claude_plugin["version"] != plugin["version"]:
        raise ValueError("Codex and Claude plugin versions must match")
    npm = json.loads((root / "package.json").read_text(encoding="utf-8"))
    versions = {
        "npm": str(npm["version"]),
        "plugin": str(plugin["version"]),
        "project": str(project["project"]["version"]),
    }
    artifacts, relationships, files = _artifact_packages(dist, versions)
    dependencies = _npm_dependencies(root / "package-lock.json")
    unique_dependencies = {
        (item["name"], item["versionInfo"]): item for item in dependencies
    }
    dependencies = [unique_dependencies[key] for key in sorted(unique_dependencies)]
    npm_artifact = next(
        (
            item
            for item in artifacts
            if item["name"].startswith("awe-tracegate-")
            and item["name"].endswith(".tgz")
        ),
        None,
    )
    if npm_artifact is not None:
        relationships.extend(
            {
                "relatedSpdxElement": item["SPDXID"],
                "relationshipType": "DEPENDS_ON",
                "spdxElementId": npm_artifact["SPDXID"],
            }
            for item in dependencies
        )

    subject_fingerprint = hashlib.sha256(
        json.dumps(
            [
                (item["name"], item["checksums"][0]["checksumValue"])
                for item in artifacts
            ],
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    created = datetime.fromtimestamp(source_date_epoch, UTC).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    sbom = {
        "SPDXID": "SPDXRef-DOCUMENT",
        "creationInfo": {
            "created": created,
            "creators": ["Tool: awe-tracegate-build-release-bundles"],
        },
        "dataLicense": "CC0-1.0",
        "documentNamespace": (
            "https://github.com/kingggg5/awe-tracegate/sbom/"
            f"sha256-{subject_fingerprint}"
        ),
        "name": f"awe-tracegate-release-{versions['project']}",
        "packages": artifacts + dependencies,
        "relationships": relationships,
        "spdxVersion": "SPDX-2.3",
    }
    if files:
        sbom["files"] = files
    _write_json(sbom_path, sbom)

    checksum_lines = []
    for path in sorted(dist.iterdir(), key=lambda item: item.name):
        if path.is_file() and path.resolve() != checksums_path.resolve():
            checksum_lines.append(f"{_sha256(path)} *{path.name}")
    checksums_path.write_text(
        "\n".join(checksum_lines) + "\n", encoding="utf-8", newline="\n"
    )


def write_gate_predicate(
    receipt_path: Path,
    subject: Path,
    evidence: tuple[tuple[str, Path], ...],
    repository: str,
    commit_sha: str,
    output: Path,
) -> None:
    from awe_tracegate.contracts import GateReceipt

    for label, path in (
        ("receipt", receipt_path),
        ("subject", subject),
        *evidence,
    ):
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"{label} must be a regular file: {path}")
    if receipt_path.stat().st_size > 16 * 1024 * 1024:
        raise ValueError("gate receipt exceeds the 16 MiB predicate limit")
    if output.is_symlink():
        raise ValueError(f"predicate output must not be a symbolic link: {output}")
    if not re.fullmatch(r"https://[^\s\x00-\x1f]+", repository):
        raise ValueError("repository must be an HTTPS URI without control characters")
    receipt = GateReceipt.model_validate_json(receipt_path.read_text(encoding="utf-8"))
    if not re.fullmatch(r"[0-9a-fA-F]{40,64}", commit_sha):
        raise ValueError("commit SHA must contain 40 to 64 hexadecimal characters")
    predicate = {
        "commit_sha": commit_sha.lower(),
        "evidence": [
            {
                "artifact_kind": kind,
                "sha256": f"sha256:{_sha256(path)}",
            }
            for kind, path in sorted(evidence)
        ],
        "gate_receipt": receipt.model_dump(mode="json", exclude_none=False),
        "repository": repository,
        "schema_version": "awe.github-gate-attestation-predicate.v1",
        "subject": {
            "name": subject.name,
            "sha256": f"sha256:{_sha256(subject)}",
        },
    }
    _write_json(output, predicate)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subcommands = parser.add_subparsers(dest="command", required=True)

    plugin = subcommands.add_parser("plugin")
    plugin.add_argument("--root", type=Path, default=Path.cwd())
    plugin.add_argument("--out", type=Path, required=True)

    metadata = subcommands.add_parser("metadata")
    metadata.add_argument("--root", type=Path, default=Path.cwd())
    metadata.add_argument("--dist", type=Path, required=True)
    metadata.add_argument("--sbom", type=Path, required=True)
    metadata.add_argument("--checksums", type=Path, required=True)
    metadata.add_argument("--source-date-epoch", type=int, required=True)

    predicate = subcommands.add_parser("predicate")
    predicate.add_argument("--receipt", type=Path, required=True)
    predicate.add_argument("--subject", type=Path, required=True)
    predicate.add_argument("--traces", type=Path, required=True)
    predicate.add_argument("--baseline", type=Path, required=True)
    predicate.add_argument("--candidate", type=Path, required=True)
    predicate.add_argument("--policy", type=Path)
    predicate.add_argument("--repository", required=True)
    predicate.add_argument("--commit-sha", required=True)
    predicate.add_argument("--out", type=Path, required=True)
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    if args.command == "plugin":
        digest = build_plugin_bundle(args.root, args.out)
        if not SHA256_PATTERN.fullmatch(digest):
            raise AssertionError("invalid plugin SHA-256")
        print(f"sha256:{digest}  {args.out}")
    elif args.command == "metadata":
        write_release_metadata(
            args.root,
            args.dist,
            args.sbom,
            args.checksums,
            args.source_date_epoch,
        )
        print(args.sbom)
        print(args.checksums)
    else:
        evidence = [
            ("execution_traces", args.traces),
            ("baseline_evaluation", args.baseline),
            ("candidate_evaluation", args.candidate),
        ]
        if args.policy is not None:
            evidence.append(("evaluation_policy", args.policy))
        write_gate_predicate(
            args.receipt,
            args.subject,
            tuple(evidence),
            args.repository,
            args.commit_sha,
            args.out,
        )
        print(args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
