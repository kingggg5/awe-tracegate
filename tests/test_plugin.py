from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from scripts.sync_claude_plugin import MANUAL_SKILLS, sync

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_SKILLS = (
    "tracegate-check",
    "tracegate-compare-change",
    "tracegate-integrate-evidence",
    "tracegate-share-evidence",
    "tracegate-verify-evidence",
)
EVIDENCE_SKILLS = set(EXPECTED_SKILLS) - {"tracegate-check"}
MANIFEST_NAME = ".awe-tracegate-managed.json"


def _python_installer(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts" / "install_skills.py"), *args],
        check=False,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_plugin_manifest_and_active_skill_inventory_are_complete() -> None:
    manifest = json.loads(
        (PROJECT_ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    claude_manifest = json.loads(
        (
            PROJECT_ROOT
            / "integrations"
            / "claude-code"
            / ".claude-plugin"
            / "plugin.json"
        ).read_text(encoding="utf-8")
    )
    package = json.loads((PROJECT_ROOT / "package.json").read_text(encoding="utf-8"))
    python_project = tomllib.loads(
        (PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    typescript_package = json.loads(
        (PROJECT_ROOT / "sdk" / "typescript" / "package.json").read_text(
            encoding="utf-8"
        )
    )
    assert {
        manifest["name"],
        claude_manifest["name"],
        package["name"],
    } == {"awe-tracegate"}
    versions = {
        manifest["version"],
        claude_manifest["version"],
        package["version"],
        python_project["project"]["version"],
        typescript_package["version"],
    }
    assert versions == {"0.3.0"}
    assert manifest["skills"] == "./skills/"
    assert "mcpServers" not in manifest
    assert "apps" not in manifest
    assert "hooks" not in claude_manifest
    assert "mcpServers" not in claude_manifest
    assert "commands" not in claude_manifest
    assert "agents" not in claude_manifest

    actual = tuple(
        sorted(
            path.name
            for path in (PROJECT_ROOT / "skills").iterdir()
            if path.is_dir() and (path / "SKILL.md").is_file()
        )
    )
    assert actual == EXPECTED_SKILLS

    for skill in EXPECTED_SKILLS:
        skill_root = PROJECT_ROOT / "skills" / skill
        instructions = (skill_root / "SKILL.md").read_text(encoding="utf-8")
        metadata = (skill_root / "agents" / "openai.yaml").read_text(encoding="utf-8")
        assert instructions.startswith(f"---\nname: {skill}\n")
        assert "[TODO" not in instructions
        assert f"$${skill}" not in metadata
        assert f"${skill}" in metadata
        expected_policy = str(skill not in EVIDENCE_SKILLS).lower()
        assert f"allow_implicit_invocation: {expected_policy}" in metadata

    for skill in EVIDENCE_SKILLS:
        instructions = (PROJECT_ROOT / "skills" / skill / "SKILL.md").read_text(
            encoding="utf-8"
        )
        assert "Untrusted-artifact protocol" in instructions
        assert "never" in instructions.lower()


def test_each_skill_has_portable_trigger_evals() -> None:
    for skill in EXPECTED_SKILLS:
        fixture = json.loads(
            (PROJECT_ROOT / "skills" / skill / "evals" / "evals.json").read_text(
                encoding="utf-8"
            )
        )
        assert fixture["skill_name"] == skill
        assert [case["id"] for case in fixture["evals"]] == [1, 2, 3, 4, 5]
        for case in fixture["evals"]:
            assert isinstance(case["prompt"], str) and case["prompt"].strip()
            assert isinstance(case["expected_output"], str)
        combined = " ".join(case["expected_output"] for case in fixture["evals"])
        assert "Does not activate" in combined or "Rejects the request" in combined
        assert "hostile" in combined or "untrusted" in combined


def test_codex_marketplace_uses_git_source_and_required_policy() -> None:
    marketplace = json.loads(
        (PROJECT_ROOT / ".agents" / "plugins" / "marketplace.json").read_text(
            encoding="utf-8"
        )
    )
    assert marketplace["name"] == "awe-tracegate"
    assert marketplace["interface"]["displayName"] == "AWE TraceGate"
    assert len(marketplace["plugins"]) == 1
    plugin = marketplace["plugins"][0]
    assert plugin["name"] == "awe-tracegate"
    assert plugin["source"] == {
        "source": "url",
        "url": "https://github.com/kingggg5/awe-tracegate.git",
        "ref": "main",
    }
    assert plugin["policy"] == {
        "installation": "AVAILABLE",
        "authentication": "ON_INSTALL",
    }
    assert plugin["category"] == "Developer Tools"


def test_claude_marketplace_reuses_the_repository_root_plugin() -> None:
    marketplace = json.loads(
        (PROJECT_ROOT / ".claude-plugin" / "marketplace.json").read_text(
            encoding="utf-8"
        )
    )
    manifest = json.loads(
        (
            PROJECT_ROOT
            / "integrations"
            / "claude-code"
            / ".claude-plugin"
            / "plugin.json"
        ).read_text(encoding="utf-8")
    )
    assert marketplace["$schema"] == (
        "https://json.schemastore.org/claude-code-marketplace.json"
    )
    assert marketplace["name"] == "awe-tracegate"
    assert marketplace["version"] == manifest["version"]
    assert marketplace["owner"] == {"name": "kingggg5"}
    assert len(marketplace["plugins"]) == 1
    plugin = marketplace["plugins"][0]
    assert plugin["name"] == manifest["name"]
    assert plugin["version"] == manifest["version"]
    assert plugin["source"] == "./integrations/claude-code"
    assert plugin["category"] == "development"


def test_claude_adapter_is_current_and_preserves_manual_evidence_invocation() -> None:
    assert sync(PROJECT_ROOT, check=True) == ()
    for skill in EXPECTED_SKILLS:
        instructions = (
            PROJECT_ROOT
            / "integrations"
            / "claude-code"
            / "skills"
            / skill
            / "SKILL.md"
        ).read_text(encoding="utf-8")
        expected = skill in MANUAL_SKILLS
        assert ("disable-model-invocation: true" in instructions) is expected
        assert "$tracegate-" not in instructions


def test_python_installer_dry_run_install_check_and_managed_hashes(
    tmp_path: Path,
) -> None:
    command = ["--target", str(tmp_path), "--skill", "tracegate-check"]

    dry_run = _python_installer(*command, "--dry-run")
    assert dry_run.returncode == 0, dry_run.stderr
    assert not (tmp_path / ".agents").exists()

    first = _python_installer(*command)
    assert first.returncode == 0, first.stderr
    installed = tmp_path / ".agents" / "skills" / "tracegate-check"
    assert (installed / "SKILL.md").is_file()

    managed_path = tmp_path / ".agents" / "skills" / MANIFEST_NAME
    managed = json.loads(managed_path.read_text(encoding="utf-8"))
    assert managed["schema_version"] == "awe.tracegate-skill-install.v1"
    record = managed["skills"]["tracegate-check"]
    assert record["package_version"] == "0.3.0"
    assert record["files"]["SKILL.md"] == _sha256(installed / "SKILL.md")

    check = _python_installer(*command, "--check")
    assert check.returncode == 0, check.stderr
    assert "Current:" in check.stdout
    second = _python_installer(*command)
    assert second.returncode == 0, second.stderr
    assert "(current)" in second.stdout

    managed["skills"]["tracegate-check"]["package_version"] = "0.2.9"
    managed_path.write_text(json.dumps(managed, indent=2) + "\n", encoding="utf-8")
    update = _python_installer(*command)
    assert update.returncode == 0, update.stderr
    assert "(update)" in update.stdout
    assert _python_installer(*command, "--check").returncode == 0
    assert not tuple((tmp_path / ".agents" / "skills").glob(".awe-tracegate-stage-*"))


def test_python_installer_refuses_unmanaged_or_modified_content(
    tmp_path: Path,
) -> None:
    unmanaged = tmp_path / "unmanaged"
    unmanaged.mkdir()
    conflict = unmanaged / ".agents" / "skills" / "tracegate-check"
    conflict.mkdir(parents=True)
    (conflict / "SKILL.md").write_text("user content\n", encoding="utf-8")
    refused = _python_installer(
        "--target", str(unmanaged), "--skill", "tracegate-check"
    )
    assert refused.returncode != 0
    assert "unmanaged skill" in refused.stderr
    assert (conflict / "SKILL.md").read_text(encoding="utf-8") == "user content\n"

    managed = tmp_path / "managed"
    managed.mkdir()
    command = ["--target", str(managed), "--skill", "tracegate-check"]
    assert _python_installer(*command).returncode == 0
    skill_file = managed / ".agents" / "skills" / "tracegate-check" / "SKILL.md"
    skill_file.write_text("local edit\n", encoding="utf-8")

    update = _python_installer(*command)
    assert update.returncode != 0
    assert "modified outside" in update.stderr
    assert skill_file.read_text(encoding="utf-8") == "local edit\n"


def test_installers_reject_symlinked_agents_parent(tmp_path: Path) -> None:
    target = tmp_path / "repository"
    outside = tmp_path / "outside"
    target.mkdir()
    outside.mkdir()
    try:
        (target / ".agents").symlink_to(outside, target_is_directory=True)
    except OSError as error:
        pytest.skip(f"directory symlinks are unavailable: {error}")

    python_result = _python_installer(
        "--target", str(target), "--skill", "tracegate-check"
    )
    assert python_result.returncode != 0
    assert "Agent destination must be a real directory" in python_result.stderr
    assert not (outside / "skills").exists()

    node = shutil.which("node")
    if node is not None:
        node_result = subprocess.run(
            [
                node,
                str(PROJECT_ROOT / "npm" / "cli.mjs"),
                "install",
                "--target",
                str(target),
                "--skill",
                "tracegate-check",
            ],
            check=False,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
        )
        assert node_result.returncode != 0
        assert "Agent destination must be a real directory" in node_result.stderr
        assert not (outside / "skills").exists()


@pytest.mark.parametrize("unknown", ["../escape", "does-not-exist"])
def test_python_installer_rejects_unknown_skill(tmp_path: Path, unknown: str) -> None:
    result = _python_installer("--target", str(tmp_path), "--skill", unknown)
    assert result.returncode != 0
    assert "Unknown skill" in result.stderr


def test_npm_package_is_zero_dependency_and_has_no_install_hooks() -> None:
    package = json.loads((PROJECT_ROOT / "package.json").read_text(encoding="utf-8"))
    lock = json.loads((PROJECT_ROOT / "package-lock.json").read_text(encoding="utf-8"))
    assert package["name"] == "awe-tracegate"
    assert lock["name"] == package["name"]
    assert lock["version"] == package["version"]
    assert package["engines"] == {"node": ">=20"}
    assert "dependencies" not in package
    assert "optionalDependencies" not in package
    scripts = package.get("scripts", {})
    assert not {"preinstall", "install", "postinstall", "prepare"}.intersection(scripts)
    assert package["bin"] == {"awe-tracegate": "npm/cli.mjs"}
    assert ".claude-plugin/marketplace.json" in package["files"]
    assert "integrations/claude-code/.claude-plugin/plugin.json" in package["files"]
    assert "integrations/claude-code/skills" in package["files"]


@pytest.mark.skipif(shutil.which("node") is None, reason="Node.js is unavailable")
def test_node_installer_matches_python_managed_manifest(tmp_path: Path) -> None:
    target = tmp_path / "repository"
    target.mkdir()
    python_install = _python_installer(
        "--target", str(target), "--skill", "tracegate-check"
    )
    assert python_install.returncode == 0, python_install.stderr

    node_check = subprocess.run(
        [
            shutil.which("node") or "node",
            str(PROJECT_ROOT / "npm" / "cli.mjs"),
            "check",
            "--target",
            str(target),
            "--skill",
            "tracegate-check",
        ],
        check=False,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    assert node_check.returncode == 0, node_check.stderr


@pytest.mark.skipif(
    shutil.which("npm") is None or shutil.which("node") is None,
    reason="npm and Node.js are required",
)
def test_npm_pack_and_local_install_smoke(tmp_path: Path) -> None:
    npm = shutil.which("npm") or "npm"
    pack_dir = tmp_path / "pack"
    cache_dir = tmp_path.parent / "npm-cache"
    consumer = tmp_path / "consumer"
    target = tmp_path / "target"
    pack_dir.mkdir()
    consumer.mkdir()
    target.mkdir()
    environment = {**os.environ, "npm_config_cache": str(cache_dir)}

    packed = subprocess.run(
        [npm, "pack", "--json", "--pack-destination", str(pack_dir)],
        cwd=PROJECT_ROOT,
        env=environment,
        check=False,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    assert packed.returncode == 0, packed.stderr
    pack_metadata = json.loads(packed.stdout)[0]
    filename = pack_metadata["filename"]
    packed_paths = {entry["path"] for entry in pack_metadata["files"]}
    for skill in EXPECTED_SKILLS:
        assert f"skills/{skill}/SKILL.md" in packed_paths
        assert f"skills/{skill}/evals/evals.json" in packed_paths
    assert not any(path.startswith("skills/awe") for path in packed_paths)
    assert ".codex-plugin/plugin.json" in packed_paths
    assert ".claude-plugin/marketplace.json" in packed_paths
    assert "integrations/claude-code/.claude-plugin/plugin.json" in packed_paths
    for skill in EXPECTED_SKILLS:
        assert f"integrations/claude-code/skills/{skill}/SKILL.md" in packed_paths
    tarball = pack_dir / filename
    assert tarball.is_file()

    installed = subprocess.run(
        [
            npm,
            "install",
            "--ignore-scripts",
            "--no-audit",
            "--no-fund",
            "--prefix",
            str(consumer),
            str(tarball),
        ],
        env=environment,
        check=False,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    assert installed.returncode == 0, installed.stderr
    executable = (
        consumer
        / "node_modules"
        / ".bin"
        / ("awe-tracegate.cmd" if os.name == "nt" else "awe-tracegate")
    )
    smoke = subprocess.run(
        [
            str(executable),
            "install",
            "--target",
            str(target),
            "--skill",
            "tracegate-check",
        ],
        env=environment,
        check=False,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    assert smoke.returncode == 0, smoke.stderr
    assert (target / ".agents" / "skills" / "tracegate-check" / "SKILL.md").is_file()
