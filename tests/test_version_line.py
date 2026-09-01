"""The version line is one line: every version this repo declares says the same thing.

The change's declared version, the CHANGELOG entry, the version files and the annotated tag
must agree or a release is three answers to "what shipped". Only the two version *files* can
be checked offline from the tree alone; the tag and the change's frontmatter are the release
station's job. This guard exists because they had already drifted a full release apart:
``__version__`` said 0.1.0 while ``pyproject.toml`` said 0.2.0.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

import synthetic_portraits

REPO_ROOT = Path(__file__).resolve().parent.parent
CHANGELOG = REPO_ROOT / "CHANGELOG.md"

_SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


def _pyproject_version() -> str:
    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())
    return data["project"]["version"]


@pytest.mark.spec_exempt("structural guard: no scenario to bind until a spec tree exists")
def test_package_version_matches_pyproject():
    assert synthetic_portraits.__version__ == _pyproject_version()


@pytest.mark.spec_exempt("structural guard: no scenario to bind until a spec tree exists")
def test_declared_version_is_semver():
    assert _SEMVER.match(_pyproject_version())


@pytest.mark.spec_exempt("structural guard: no scenario to bind until a spec tree exists")
def test_changelog_keeps_an_unreleased_section_for_the_next_phase_entry():
    assert "## [Unreleased]" in CHANGELOG.read_text()


@pytest.mark.spec_exempt("structural guard: no scenario to bind until a spec tree exists")
def test_changelog_records_every_released_tag():
    """Every annotated tag must already have a section, so a release cannot skip its entry."""
    text = CHANGELOG.read_text()
    released = ["0.1.0", "0.2.0"]
    assert [v for v in released if f"## [{v}]" not in text] == []
