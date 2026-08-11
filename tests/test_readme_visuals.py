from __future__ import annotations

import re
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


def test_readme_discovery_walkthrough_steps_stay_inside_the_panel() -> None:
    """Prevent the final walkthrough step from overlapping the panel footer."""

    asset = PROJECT_ROOT / "docs" / "assets" / "awe-discovery-loop-demo.svg"
    root = ElementTree.fromstring(asset.read_text(encoding="utf-8"))
    namespace = "{http://www.w3.org/2000/svg}"
    panel = next(
        group
        for group in root.iter(f"{namespace}g")
        if group.get("transform") == "translate(56 126)"
    )
    panel_rect = next(child for child in panel if child.tag == f"{namespace}rect")
    panel_height = int(panel_rect.get("height", "0"))
    step_bounds = []
    for group in panel.findall(f"{namespace}g"):
        match = re.fullmatch(r"translate\(34 (\d+)\)", group.get("transform", ""))
        if not match:
            continue
        step = next((child for child in group if child.tag == f"{namespace}rect"), None)
        if step is None or step.get("width") != "1008":
            continue
        step_bounds.append((int(match.group(1)), int(step.get("height", "0"))))

    assert step_bounds == [(76, 72), (190, 86), (320, 72)]
    assert all(offset + height <= panel_height - 20 for offset, height in step_bounds)
