"""Shared test fixtures."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS_DIR = REPO_ROOT / "workflows"


@pytest.fixture
def txt2img_workflow() -> dict:
    """The placeholder RealVisXL txt2img API-format graph (golden fixture)."""
    return json.loads((WORKFLOWS_DIR / "realvis-txt2img.json").read_text())


@pytest.fixture
def identity_workflow() -> dict:
    """The placeholder RealVisXL + InstantID identity graph (golden fixture)."""
    return json.loads((WORKFLOWS_DIR / "realvis-txt2img-identity.json").read_text())
