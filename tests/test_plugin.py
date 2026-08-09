from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_SKILLS = (
    "awe",
    "awe-diagnose-regression",
    "awe-discovery-loop",
    "awe-review-evidence",
    "awe-setup",
)
IMPLICIT_SKILLS = {"awe-diagnose-regression"}


def test_plugin_manifest_and_skill_inventory_are_complete() -> None:
    manifest = json.loads(
        (PROJECT_ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    assert manifest["name"] == "awe-tracegate"
    assert manifest["skills"] == "./skills/"

    skill_paths = (PROJECT_ROOT / "skills").iterdir()
    actual = tuple(sorted(path.name for path in skill_paths if path.is_dir()))
    assert actual == EXPECTED_SKILLS

    for skill in EXPECTED_SKILLS:
        skill_root = PROJECT_ROOT / "skills" / skill
        instructions = (skill_root / "SKILL.md").read_text(encoding="utf-8")
        metadata = (skill_root / "agents" / "openai.yaml").read_text(encoding="utf-8")
        assert instructions.startswith(f"---\nname: {skill}\n")
        assert "[TODO" not in instructions
        expected_policy = str(skill in IMPLICIT_SKILLS).lower()
        assert f"allow_implicit_invocation: {expected_policy}" in metadata

    router = (PROJECT_ROOT / "skills" / "awe" / "SKILL.md").read_text(encoding="utf-8")
    for skill in EXPECTED_SKILLS[1:]:
        assert f"${skill}" in router


def test_installer_copies_selected_skill_and_refuses_implicit_overwrite(
    tmp_path: Path,
) -> None:
    installer = PROJECT_ROOT / "scripts" / "install_skills.py"
    command = [
        sys.executable,
        str(installer),
        "--target",
        str(tmp_path),
        "--skill",
        "awe-discovery-loop",
    ]

    first = subprocess.run(command, check=False, capture_output=True, text=True)
    assert first.returncode == 0, first.stderr
    installed = tmp_path / ".agents" / "skills" / "awe-discovery-loop" / "SKILL.md"
    assert installed.is_file()

    second = subprocess.run(command, check=False, capture_output=True, text=True)
    assert second.returncode != 0
    assert "already exists" in second.stderr

    forced = subprocess.run(
        [*command, "--force"], check=False, capture_output=True, text=True
    )
    assert forced.returncode == 0, forced.stderr


@pytest.mark.parametrize("unknown", ["../escape", "does-not-exist"])
def test_installer_rejects_unknown_skill(tmp_path: Path, unknown: str) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(PROJECT_ROOT / "scripts" / "install_skills.py"),
            "--target",
            str(tmp_path),
            "--skill",
            unknown,
        ],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "Unknown skill" in result.stderr
