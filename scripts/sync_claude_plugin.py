"""Synchronize the Claude Code Skill adapter from canonical Agent Skills."""

from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path

PLUGIN_NAME = "awe-tracegate"
MANUAL_SKILLS = {
    "tracegate-compare-change",
    "tracegate-integrate-evidence",
    "tracegate-share-evidence",
    "tracegate-verify-evidence",
}
SKILL_INVOCATION = re.compile(r"\$((?:tracegate-)(?:[a-z0-9-]+|\*))")


def _render_skill(source: Path, manual: bool) -> str:
    text = source.read_text(encoding="utf-8")
    if not text.startswith("---\n"):
        raise ValueError(f"missing frontmatter: {source}")
    boundary = text.find("\n---\n", 4)
    if boundary < 0:
        raise ValueError(f"invalid frontmatter: {source}")
    frontmatter = text[4:boundary].splitlines()
    keys = {line.partition(":")[0].strip() for line in frontmatter if ":" in line}
    if keys != {"name", "description"}:
        raise ValueError(f"canonical Skill frontmatter changed: {source}")
    if manual:
        frontmatter.append("disable-model-invocation: true")
    body = text[boundary + 5 :]
    body = SKILL_INVOCATION.sub(rf"/{PLUGIN_NAME}:\1", body)
    return "---\n" + "\n".join(frontmatter) + "\n---\n" + body


def _expected_files(root: Path) -> dict[Path, bytes]:
    expected: dict[Path, bytes] = {}
    for skill_root in sorted((root / "skills").iterdir(), key=lambda path: path.name):
        skill_file = skill_root / "SKILL.md"
        if not skill_root.is_dir() or not skill_file.is_file():
            continue
        output_root = root / "integrations" / "claude-code" / "skills" / skill_root.name
        expected[output_root / "SKILL.md"] = _render_skill(
            skill_file, skill_root.name in MANUAL_SKILLS
        ).encode("utf-8")
        references = skill_root / "references"
        if references.is_dir():
            for source in sorted(references.rglob("*")):
                if source.is_symlink():
                    raise ValueError(f"Claude adapter refuses symbolic link: {source}")
                if source.is_file():
                    output = output_root / "references" / source.relative_to(references)
                    expected[output] = source.read_bytes()
    if not expected:
        raise ValueError("no canonical Skills found")
    return expected


def sync(root: Path, *, check: bool) -> tuple[str, ...]:
    root = root.resolve(strict=True)
    plugin_root = root / "integrations" / "claude-code"
    output_root = plugin_root / "skills"
    expected = _expected_files(root)
    linked_root = next(
        (path for path in (plugin_root, output_root) if path.is_symlink()), None
    )
    if linked_root is not None:
        raise ValueError(
            f"Claude adapter output must be a real directory: {linked_root}"
        )
    if output_root.is_dir():
        linked = next(
            (path for path in output_root.rglob("*") if path.is_symlink()), None
        )
        if linked is not None:
            raise ValueError(f"Claude adapter refuses symbolic link: {linked}")
    existing = (
        {path for path in output_root.rglob("*") if path.is_file()}
        if output_root.is_dir()
        else set()
    )
    unexpected = sorted(existing - set(expected))
    if unexpected:
        relative = ", ".join(path.relative_to(root).as_posix() for path in unexpected)
        raise ValueError(f"unexpected Claude adapter files: {relative}")

    changed = tuple(
        path.relative_to(root).as_posix()
        for path, payload in expected.items()
        if not path.is_file() or path.read_bytes() != payload
    )
    if check:
        if changed:
            raise ValueError("Claude adapter is stale: " + ", ".join(changed))
        return ()

    for path, payload in expected.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.tmp")
        temporary.write_bytes(payload)
        if path.exists():
            shutil.copymode(path, temporary)
        temporary.replace(path)
    return changed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true")
    mode.add_argument("--write", action="store_true")
    args = parser.parse_args()
    try:
        changed = sync(args.root, check=args.check)
    except (OSError, ValueError) as error:
        parser.exit(1, f"error: {error}\n")
    print("Claude adapter is current" if not changed else "\n".join(changed))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
