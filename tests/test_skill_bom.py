from __future__ import annotations

from pathlib import Path

import pytest

from awe_tracegate.skill_bom import inspect_skill


def _write_skill(root: Path) -> Path:
    skill = root / "evidence-review"
    (skill / "scripts").mkdir(parents=True)
    (skill / "references").mkdir()
    (skill / "SKILL.md").write_text(
        "---\nname: evidence-review\ndescription: Review receipts.\n---\n"
        "See https://agentskills.io/specification.\n",
        encoding="utf-8",
    )
    (skill / "scripts/check.py").write_text("print('not executed')\n", encoding="utf-8")
    (skill / "references/contract.md").write_text("Receipt v1\n", encoding="utf-8")
    return skill


def test_skill_bom_is_deterministic_and_non_executing(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path)

    first = inspect_skill(skill)
    second = inspect_skill(skill)

    assert first == second
    assert [item.path for item in first.files] == [
        "SKILL.md",
        "references/contract.md",
        "scripts/check.py",
    ]
    assert first.external_urls == ("https://agentskills.io/specification",)
    assert next(
        item for item in first.files if item.path == "scripts/check.py"
    ).role == ("script")


def test_skill_bom_changes_when_content_changes(tmp_path: Path) -> None:
    skill = _write_skill(tmp_path)
    before = inspect_skill(skill)

    (skill / "references/contract.md").write_text("Receipt v2\n", encoding="utf-8")
    after = inspect_skill(skill)

    assert after.skill_digest != before.skill_digest
    assert after.bom_digest != before.bom_digest


def test_skill_inspection_requires_standard_entrypoint(tmp_path: Path) -> None:
    skill = tmp_path / "missing-entrypoint"
    skill.mkdir()

    with pytest.raises(ValueError, match=r"SKILL\.md"):
        inspect_skill(skill)


def test_skill_name_must_be_portable(tmp_path: Path) -> None:
    skill = tmp_path / "Not Portable"
    skill.mkdir()
    (skill / "SKILL.md").write_text("instructions\n", encoding="utf-8")

    with pytest.raises(ValueError, match="string_pattern_mismatch"):
        inspect_skill(skill)
