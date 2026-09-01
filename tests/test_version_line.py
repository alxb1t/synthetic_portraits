"""The version line is one line: every version this repo declares says the same thing.

The change's declared version, the CHANGELOG entry, the version files and the annotated tag
must agree, or a release is three answers to "what shipped". This guard exists because they
had already drifted a full release apart: ``__version__`` said 0.1.0 while ``pyproject.toml``
said 0.2.0, and nothing read ``__version__``, which is why it rotted unnoticed.

The released set is derived from the tags rather than listed, since a hand-maintained mirror
of ``git tag`` is the very drift this module exists to catch.
"""

from __future__ import annotations

import functools
import re
import subprocess
import tomllib

import pytest
from conftest import REPO_ROOT, STRUCTURAL_GUARD

import synthetic_portraits

pytestmark = STRUCTURAL_GUARD

CHANGELOG = REPO_ROOT / "CHANGELOG.md"
_SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


@functools.cache
def _pyproject_version() -> str:
    data = tomllib.loads((REPO_ROOT / "pyproject.toml").read_text())
    return data["project"]["version"]


@functools.cache
def _released_versions() -> tuple[str, ...]:
    tags = subprocess.run(
        ["git", "tag", "--list", "v*"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    return tuple(tag.lstrip("v") for tag in tags)


def test_the_package_and_pyproject_declare_the_same_semver_version():
    version = _pyproject_version()
    assert _SEMVER.match(version), f"not semver: {version!r}"
    assert synthetic_portraits.__version__ == version


def test_the_changelog_keeps_an_unreleased_section_for_the_next_phase_entry():
    assert "## [Unreleased]" in CHANGELOG.read_text()


def test_the_changelog_records_every_released_tag():
    """A release cannot skip its changelog entry, for any tag that exists."""
    released = _released_versions()
    if not released:
        pytest.skip("no tags in this checkout (CI does not fetch tags by default)")
    text = CHANGELOG.read_text()
    assert [v for v in released if f"## [{v}]" not in text] == []
