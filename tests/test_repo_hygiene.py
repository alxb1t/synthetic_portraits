"""The repository resolves no path outside itself, and leaks none into tracked prose.

This repo is public. Two failures it guards against: a real absolute path from whatever
machine a run happened on (the operator's home, or the repository's own root) transcribed
into a tracked file, and a reference to the private Obsidian vault that once held the plan
of record.

Both patterns are **constructed at run time**, never written literally, for two reasons.
A literal would make this file match its own assertion; and a path a fixture constructs is
not what the rule targets — a *rendered* one, carrying a real username, is.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

# The change record under openspec/changes/ is prose *about* removing the vault coupling,
# so it necessarily names it. The absolute-path rules below hold for it regardless; only
# the two name-mention rules exempt it.
_NAME_RULE_EXEMPT = ("openspec/changes/", "tests/test_repo_hygiene.py")

# Assembled rather than spelled, so this file does not match itself.
_VAULT_ENV_VAR = "VAULT_" + "PROJECT_DIR"
_VAULT_WORD = "va" + "ult"


def _tracked_files() -> list[str]:
    """Every file git would carry: tracked, plus untracked-and-not-ignored.

    ``--others --exclude-standard`` is load-bearing. Listing only tracked files let a
    newly written file pass this guard until its first commit, so the gate went green on
    an incomplete set and the violation surfaced one phase later.
    """
    out = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return sorted({p for p in out.split("\0") if p and (REPO_ROOT / p).is_file()})


def _read(path: str) -> str:
    return (REPO_ROOT / path).read_bytes().decode("utf-8", errors="ignore")


def _offenders(needle: str, *, exempt: tuple[str, ...] = ()) -> list[str]:
    return [
        path for path in _tracked_files() if not path.startswith(exempt) if needle in _read(path)
    ]


@pytest.mark.spec_exempt("structural guard: no scenario to bind until a spec tree exists")
def test_no_tracked_file_contains_the_operators_home_directory():
    home = str(Path.home())
    assert _offenders(home) == []


@pytest.mark.spec_exempt("structural guard: no scenario to bind until a spec tree exists")
def test_no_tracked_file_contains_this_repositorys_own_absolute_root():
    assert _offenders(str(REPO_ROOT)) == []


@pytest.mark.spec_exempt("structural guard: no scenario to bind until a spec tree exists")
def test_no_tracked_file_declares_the_vault_environment_variable():
    assert _offenders(_VAULT_ENV_VAR, exempt=_NAME_RULE_EXEMPT) == []


@pytest.mark.spec_exempt("structural guard: no scenario to bind until a spec tree exists")
def test_no_tracked_file_outside_the_change_record_mentions_the_private_vault():
    offenders = [
        path
        for path in _tracked_files()
        if not path.startswith(_NAME_RULE_EXEMPT)
        if _VAULT_WORD in _read(path).lower()
    ]
    assert offenders == []
