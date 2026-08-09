from __future__ import annotations

import argparse
import shutil
from collections.abc import Sequence
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SKILLS_ROOT = REPOSITORY_ROOT / "skills"


def available_skills() -> tuple[str, ...]:
    return tuple(sorted(path.name for path in SKILLS_ROOT.iterdir() if path.is_dir()))


def install_skills(
    target: Path,
    selected: Sequence[str] = (),
    *,
    force: bool = False,
) -> tuple[Path, tuple[str, ...]]:
    target = target.resolve()
    if not target.is_dir():
        raise ValueError(f"Target repository is not a directory: {target}")

    known = available_skills()
    skills = tuple(dict.fromkeys(selected)) if selected else known
    unknown = tuple(skill for skill in skills if skill not in known)
    if unknown:
        raise ValueError(
            f"Unknown skill: {', '.join(unknown)}. Available: {', '.join(known)}"
        )

    destination_root = target / ".agents" / "skills"
    destinations = tuple(destination_root / skill for skill in skills)
    conflicts = tuple(path for path in destinations if path.exists())
    if conflicts and not force:
        raise ValueError(
            "Skill already exists: "
            f"{', '.join(str(path) for path in conflicts)}. "
            "Re-run with --force to replace the selected skill."
        )

    destination_root.mkdir(parents=True, exist_ok=True)
    for skill, destination in zip(skills, destinations, strict=True):
        if force:
            shutil.rmtree(destination, ignore_errors=True)
        shutil.copytree(SKILLS_ROOT / skill, destination)
    return destination_root, skills


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Install AWE TraceGate skills into another repository."
    )
    parser.add_argument("--target", type=Path, help="target repository path")
    parser.add_argument(
        "--skill",
        action="append",
        default=[],
        help="install one skill; repeat to select multiple skills",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="replace only the selected skill directories",
    )
    parser.add_argument("--list", action="store_true", help="list available skills")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.list:
        print("\n".join(available_skills()))
        return 0
    if args.target is None:
        raise SystemExit("--target is required unless --list is used")

    try:
        destination, skills = install_skills(
            args.target,
            args.skill,
            force=args.force,
        )
    except ValueError as error:
        raise SystemExit(str(error)) from error
    print(f"Installed {', '.join(skills)} to {destination}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
