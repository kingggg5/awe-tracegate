"""Non-executing, content-addressed inventory for portable Agent Skills."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Literal

from .contracts import PENDING_SHA256_DIGEST, SkillBom, SkillFile, canonical_digest

_URL_PATTERN = re.compile(r"https?://[^\s<>()\[\]{}\"']+")
_TEXT_SUFFIXES = frozenset(
    {
        ".json",
        ".md",
        ".ps1",
        ".py",
        ".sh",
        ".toml",
        ".ts",
        ".txt",
        ".yaml",
        ".yml",
    }
)
_MAX_FILE_BYTES = 100_000_000
_MAX_URL_SCAN_BYTES = 2_000_000


def _role(
    path: str,
) -> Literal["instructions", "metadata", "script", "reference", "asset", "other"]:
    if path == "SKILL.md":
        return "instructions"
    if path == "agents/openai.yaml":
        return "metadata"
    top_level = path.partition("/")[0]
    if top_level == "assets":
        return "asset"
    if top_level == "references":
        return "reference"
    if top_level == "scripts":
        return "script"
    return "other"


def _digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"


def _external_urls(path: Path) -> set[str]:
    if path.suffix.lower() not in _TEXT_SUFFIXES:
        return set()
    size = path.stat().st_size
    if size > _MAX_URL_SCAN_BYTES:
        return set()
    text = path.read_text(encoding="utf-8", errors="ignore")
    return {match.rstrip(".,;:") for match in _URL_PATTERN.findall(text)}


def inspect_skill(skill_directory: Path) -> SkillBom:
    """Hash a skill folder without importing or executing any of its content."""

    if not skill_directory.is_dir():
        raise ValueError(f"skill directory does not exist: {skill_directory}")
    if skill_directory.is_symlink():
        raise ValueError("skill directory cannot be a symbolic link")
    if not (skill_directory / "SKILL.md").is_file():
        raise ValueError("skill directory must contain SKILL.md")

    files: list[SkillFile] = []
    urls: set[str] = set()
    for path in sorted(skill_directory.rglob("*")):
        relative = path.relative_to(skill_directory)
        if ".git" in relative.parts:
            continue
        if path.is_symlink():
            raise ValueError(f"skill content cannot be a symbolic link: {relative}")
        if not path.is_file():
            continue
        size = path.stat().st_size
        if size > _MAX_FILE_BYTES:
            raise ValueError(f"skill file exceeds 100 MB limit: {relative}")
        portable_path = relative.as_posix()
        files.append(
            SkillFile(
                path=portable_path,
                digest=_digest_file(path),
                size_bytes=size,
                role=_role(portable_path),
            )
        )
        urls.update(_external_urls(path))

    files.sort(key=lambda item: item.path)
    skill_digest = canonical_digest([item.model_dump(mode="json") for item in files])
    bom = SkillBom.model_construct(
        schema_version="awe.skill-bom.v1",
        skill_name=skill_directory.name,
        files=tuple(files),
        external_urls=tuple(sorted(urls)),
        skill_digest=skill_digest,
        bom_digest=PENDING_SHA256_DIGEST,
    )
    payload = bom.model_dump(mode="json", exclude={"bom_digest"})
    return SkillBom.model_validate({**payload, "bom_digest": canonical_digest(payload)})
