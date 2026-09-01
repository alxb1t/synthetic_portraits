"""The repository resolves no path outside itself, and leaks none into tracked prose.

This repo is public. Two failures it guards against: a real absolute path from whatever
machine a run happened on (the operator's home, or the repository's own root) transcribed
into a file, and a reference to the private Obsidian vault that once held the plan of record.

This module necessarily names what it forbids, so it exempts itself — by a path **computed**
from ``__file__``, not spelled, so that renaming or moving this file cannot turn the guard
red on itself. The change record under ``openspec/changes/`` is exempt from the two
name-mention rules for the same reason: it is prose *about* removing the coupling. The two
absolute-path rules carry no exemption at all.
"""

from __future__ import annotations

import functools
import subprocess
from pathlib import Path

from conftest import REPO_ROOT, STRUCTURAL_GUARD

pytestmark = STRUCTURAL_GUARD

_SELF = Path(__file__).resolve().relative_to(REPO_ROOT).as_posix()
_NAME_RULE_EXEMPT = ("openspec/changes/", _SELF)

_VAULT_ENV_VAR = "VAULT_PROJECT_DIR"
_VAULT_WORD = "vault"


@functools.cache
def _repo_text() -> dict[str, str]:
    """Every file git would carry, decoded once per session: path -> text.

    ``--others --exclude-standard`` is load-bearing. Listing only tracked files let a newly
    written file pass this guard until its first commit, so the gate went green on an
    incomplete set and the violation surfaced a phase later.

    Files holding a NUL byte are skipped as binary. That is not only a speed concern: the
    six PNGs under ``examples/`` are ~97% of the repository's bytes and cannot meaningfully
    contain any needle below, so decoding them would be pure waste on every assertion.
    """
    out = subprocess.run(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    texts: dict[str, str] = {}
    for path in sorted({p for p in out.split("\0") if p}):
        file = REPO_ROOT / path
        if not file.is_file():
            continue
        raw = file.read_bytes()
        if b"\0" in raw:
            continue
        texts[path] = raw.decode("utf-8", errors="ignore")
    return texts


def _offenders(needle: str, *, exempt: tuple[str, ...] = (), fold_case: bool = False) -> list[str]:
    probe = needle.lower() if fold_case else needle
    return [
        path
        for path, text in _repo_text().items()
        if not path.startswith(exempt) and probe in (text.lower() if fold_case else text)
    ]


def test_no_file_contains_the_operators_home_directory():
    assert _offenders(str(Path.home())) == []


def test_no_file_contains_this_repositorys_own_absolute_root():
    assert _offenders(str(REPO_ROOT)) == []


def test_no_file_declares_the_vault_environment_variable():
    assert _offenders(_VAULT_ENV_VAR, exempt=_NAME_RULE_EXEMPT) == []


def test_no_file_outside_the_change_record_mentions_the_private_vault():
    assert _offenders(_VAULT_WORD, exempt=_NAME_RULE_EXEMPT, fold_case=True) == []
