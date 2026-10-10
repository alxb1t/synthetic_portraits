"""Shared test fixtures."""

from __future__ import annotations

import functools
import json
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS_DIR = REPO_ROOT / "workflows"
MODELS_MANIFEST = REPO_ROOT / "config" / "models.json"

# Structural guards assert a property of the repository rather than a behaviour of the
# system, so they have no spec scenario to bind. Declared once here; the guard modules
# apply it module-wide via `pytestmark`.
STRUCTURAL_GUARD = pytest.mark.spec_exempt(
    "structural guard: asserts a property of the repository, not a behaviour a scenario names"
)


@functools.cache
def repo_files() -> tuple[str, ...]:
    """Return every path git would carry, tracked or not yet, sorted.

    ``--others --exclude-standard`` is load-bearing: listing only tracked files lets a newly
    written file pass a guard until its first commit.
    """
    out = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return tuple(sorted({path for path in out.split("\0") if path}))


@pytest.fixture
def txt2img_workflow() -> dict:
    """The placeholder RealVisXL txt2img API-format graph (golden fixture)."""
    return json.loads((WORKFLOWS_DIR / "realvis-txt2img.json").read_text())


@pytest.fixture
def identity_workflow() -> dict:
    """The placeholder RealVisXL + InstantID identity graph (golden fixture)."""
    return json.loads((WORKFLOWS_DIR / "realvis-txt2img-identity.json").read_text())
