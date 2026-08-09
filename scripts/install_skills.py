from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath
from typing import Any

PACKAGE_VERSION = "0.3.0"
SCHEMA_VERSION = "awe.tracegate-skill-install.v1"
MANIFEST_NAME = ".awe-tracegate-managed.json"
SKILL_NAME = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SKILLS_ROOT = REPOSITORY_ROOT / "skills"
ACTIVE_SKILLS = (
    "tracegate-check",
    "tracegate-compare-change",
    "tracegate-integrate-evidence",
    "tracegate-share-evidence",
    "tracegate-verify-evidence",
)


class InstallError(ValueError):
    """Raised when an install would overwrite content TraceGate does not own."""


def available_skills() -> tuple[str, ...]:
    missing = tuple(
        name
        for name in ACTIVE_SKILLS
        if not (SKILLS_ROOT / name / "SKILL.md").is_file()
    )
    if missing:
        raise InstallError(f"Package is missing active skills: {', '.join(missing)}")
    return ACTIVE_SKILLS


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_link_like(path: Path) -> bool:
    if path.is_symlink():
        return True
    if os.name != "nt":
        return False
    try:
        attributes = path.lstat().st_file_attributes
    except (AttributeError, OSError):
        return False
    return bool(attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT)


def _relative_file(path: Path, root: Path) -> str:
    relative = path.relative_to(root)
    if any(part in {"", ".", ".."} for part in relative.parts):
        raise InstallError(f"Unsafe package path: {relative}")
    return relative.as_posix()


def _file_hashes(root: Path) -> dict[str, str]:
    if not root.is_dir() or _is_link_like(root):
        raise InstallError(f"Skill source must be a real directory: {root}")

    hashes: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if _is_link_like(path):
            raise InstallError(f"Skill packages cannot contain symlinks: {path}")
        if path.is_file():
            hashes[_relative_file(path, root)] = _sha256(path)
    if "SKILL.md" not in hashes:
        raise InstallError(f"Skill package has no SKILL.md: {root}")
    return hashes


def _safe_manifest_path(value: str) -> bool:
    path = PurePosixPath(value)
    return (
        bool(value)
        and not path.is_absolute()
        and ".." not in path.parts
        and "." not in path.parts
        and "\\" not in value
    )


def _empty_manifest() -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "installer_version": PACKAGE_VERSION,
        "skills": {},
    }


def _load_manifest(path: Path) -> dict[str, Any]:
    if not path.exists():
        return _empty_manifest()
    if _is_link_like(path) or not path.is_file():
        raise InstallError(f"Managed manifest must be a regular file: {path}")

    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise InstallError(f"Managed manifest is unreadable: {path}") from error

    if (
        not isinstance(document, dict)
        or document.get("schema_version") != SCHEMA_VERSION
    ):
        raise InstallError(f"Unsupported managed manifest: {path}")
    skills = document.get("skills")
    if not isinstance(skills, dict):
        raise InstallError(f"Managed manifest has an invalid skills map: {path}")

    for name, record in skills.items():
        if not isinstance(name, str) or not SKILL_NAME.fullmatch(name):
            raise InstallError(f"Managed manifest has an invalid skill name: {name!r}")
        if not isinstance(record, dict) or not isinstance(record.get("files"), dict):
            raise InstallError(f"Managed manifest has an invalid record for {name}")
        for relative, digest in record["files"].items():
            if (
                not isinstance(relative, str)
                or not _safe_manifest_path(relative)
                or not isinstance(digest, str)
                or not re.fullmatch(r"[0-9a-f]{64}", digest)
            ):
                raise InstallError(f"Managed manifest has an invalid file for {name}")
    return document


def _assert_managed_tree(destination: Path, expected: Mapping[str, str]) -> None:
    if not destination.is_dir() or _is_link_like(destination):
        raise InstallError(f"Managed skill is missing or unsafe: {destination}")
    actual = _file_hashes(destination)
    if actual != dict(expected):
        raise InstallError(
            f"Managed skill was modified outside the installer: {destination}. "
            "Back up or remove the local changes before updating it."
        )


def _selected_skills(selected: Sequence[str]) -> tuple[str, ...]:
    known = available_skills()
    skills = tuple(dict.fromkeys(selected)) if selected else known
    unknown = tuple(skill for skill in skills if skill not in known)
    if unknown:
        raise InstallError(
            f"Unknown skill: {', '.join(unknown)}. Available: {', '.join(known)}"
        )
    return skills


def _source_records(skills: Sequence[str]) -> dict[str, dict[str, Any]]:
    return {
        skill: {
            "package_version": PACKAGE_VERSION,
            "files": _file_hashes(SKILLS_ROOT / skill),
        }
        for skill in skills
    }


def _validate_target(target: Path) -> Path:
    target = target.expanduser().resolve()
    if not target.is_dir():
        raise InstallError(f"Target repository is not a directory: {target}")
    return target


def _plan(
    target: Path, selected: Sequence[str]
) -> tuple[Path, dict[str, Any], dict[str, dict[str, Any]], tuple[str, ...]]:
    target = _validate_target(target)
    skills = _selected_skills(selected)
    agents_root = target / ".agents"
    if agents_root.exists() and (
        _is_link_like(agents_root) or not agents_root.is_dir()
    ):
        raise InstallError(f"Agent destination must be a real directory: {agents_root}")
    destination_root = target / ".agents" / "skills"
    if destination_root.exists() and (
        _is_link_like(destination_root) or not destination_root.is_dir()
    ):
        raise InstallError(
            f"Skill destination must be a real directory: {destination_root}"
        )

    manifest_path = destination_root / MANIFEST_NAME
    manifest = _load_manifest(manifest_path)
    records = _source_records(skills)
    managed = manifest["skills"]
    actions: list[str] = []

    for skill in skills:
        destination = destination_root / skill
        record = managed.get(skill)
        if destination.exists() and record is None:
            raise InstallError(
                f"Refusing to overwrite unmanaged skill: {destination}. "
                "Move it aside or choose another target."
            )
        if record is not None:
            _assert_managed_tree(destination, record["files"])
        action = (
            "current" if record == records[skill] else "update" if record else "install"
        )
        actions.append(action)

    return destination_root, manifest, records, tuple(actions)


def check_skills(target: Path, selected: Sequence[str] = ()) -> tuple[str, ...]:
    _, _, _, actions = _plan(target, selected)
    not_current = tuple(action for action in actions if action != "current")
    if not_current:
        raise InstallError("Installed skills are missing or do not match this package")
    return _selected_skills(selected)


def install_skills(
    target: Path,
    selected: Sequence[str] = (),
    *,
    dry_run: bool = False,
) -> tuple[Path, tuple[str, ...], tuple[str, ...]]:
    destination_root, manifest, records, actions = _plan(target, selected)
    skills = _selected_skills(selected)
    if dry_run or all(action == "current" for action in actions):
        return destination_root, skills, actions

    destination_root.mkdir(parents=True, exist_ok=True)
    stage_root = Path(
        tempfile.mkdtemp(prefix=".awe-tracegate-stage-", dir=destination_root)
    )
    backup_root = stage_root / ".backup"
    installed: list[tuple[Path, Path | None]] = []
    manifest_path = destination_root / MANIFEST_NAME

    try:
        for skill, action in zip(skills, actions, strict=True):
            if action == "current":
                continue
            staged = stage_root / skill
            shutil.copytree(SKILLS_ROOT / skill, staged)
            if _file_hashes(staged) != records[skill]["files"]:
                raise InstallError(f"Staged skill failed digest verification: {skill}")

        backup_root.mkdir()
        for skill, action in zip(skills, actions, strict=True):
            if action == "current":
                continue
            destination = destination_root / skill
            backup: Path | None = None
            if destination.exists():
                backup = backup_root / skill
                os.replace(destination, backup)
            installed.append((destination, backup))
            os.replace(stage_root / skill, destination)

        updated = dict(manifest)
        updated["installer_version"] = PACKAGE_VERSION
        updated_skills = dict(manifest["skills"])
        updated_skills.update(records)
        updated["skills"] = updated_skills
        temporary_manifest = stage_root / MANIFEST_NAME
        temporary_manifest.write_text(
            json.dumps(updated, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        os.replace(temporary_manifest, manifest_path)
    except Exception:
        for destination, backup in reversed(installed):
            if destination.exists():
                shutil.rmtree(destination)
            if backup is not None and backup.exists():
                os.replace(backup, destination)
        raise
    finally:
        shutil.rmtree(stage_root, ignore_errors=True)

    return destination_root, skills, actions


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Install the AWE TraceGate agent skills without installing dependencies "
            "or running project code."
        )
    )
    parser.add_argument("--target", type=Path, help="target repository path")
    parser.add_argument(
        "--skill",
        action="append",
        default=[],
        help="install one active skill; repeat to select multiple skills",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--check",
        action="store_true",
        help="verify the selected installed skills without changing files",
    )
    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="validate and show the install plan without changing files",
    )
    parser.add_argument("--list", action="store_true", help="list active skills")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.list:
        print("\n".join(available_skills()))
        return 0
    if args.target is None:
        raise SystemExit("--target is required unless --list is used")

    try:
        if args.check:
            skills = check_skills(args.target, args.skill)
            print(f"Current: {', '.join(skills)}")
            return 0
        destination, skills, actions = install_skills(
            args.target, args.skill, dry_run=args.dry_run
        )
    except InstallError as error:
        raise SystemExit(str(error)) from error

    verb = "Would install" if args.dry_run else "Installed"
    plan = ", ".join(
        f"{skill} ({action})" for skill, action in zip(skills, actions, strict=True)
    )
    print(f"{verb}: {plan}\nDestination: {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
