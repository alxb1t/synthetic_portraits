"""Shared test fixtures."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS_DIR = REPO_ROOT / "workflows"

# Structural guards assert a property of the repository rather than a behaviour of the
# system, so they have no spec scenario to bind. Declared once here; the guard modules
# apply it module-wide via `pytestmark`.
STRUCTURAL_GUARD = pytest.mark.spec_exempt(
    "structural guard: asserts a property of the repository, not a behaviour a scenario names"
)


@pytest.fixture
def txt2img_workflow() -> dict:
    """The placeholder RealVisXL txt2img API-format graph (golden fixture)."""
    return json.loads((WORKFLOWS_DIR / "realvis-txt2img.json").read_text())


@pytest.fixture
def identity_workflow() -> dict:
    """The placeholder RealVisXL + InstantID identity graph (golden fixture)."""
    return json.loads((WORKFLOWS_DIR / "realvis-txt2img-identity.json").read_text())
