from __future__ import annotations

from pathlib import Path
from xml.etree import ElementTree

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_readme_discovery_walkthrough_is_present_and_valid_svg() -> None:
    """Keep the README demo tied to a renderable, honesty-labelled asset."""

    readme = (PROJECT_ROOT / "README.md").read_text(encoding="utf-8")
    asset = PROJECT_ROOT / "docs" / "assets" / "awe-discovery-loop-demo.svg"
    payload = asset.read_text(encoding="utf-8")

    assert "docs/assets/awe-discovery-loop-demo.svg" in readme
    assert "included synthetic CLI fixture" in readme
    assert "not an LLM session" in readme
    assert "<animate" in payload
    ElementTree.fromstring(payload)
