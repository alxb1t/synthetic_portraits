"""Batch orchestration helpers: parse a prompt list, slugify for stable filenames.

``--prompts <file>`` runs the selected path once per line through the regenerate loop,
writing a labeled set. These unit-test the pure helpers; the end-to-end batch behaviour
(dispatch, upload, naming, `-n`, mutual exclusion) is driven through the CLI in test_cli.
"""

from __future__ import annotations

import pytest

from synthetic_portraits.batch import read_prompts, slugify


def test_read_prompts_one_per_line_dropping_blanks(tmp_path):
    f = tmp_path / "prompts.txt"
    f.write_text("a woman in a park\n\n  a man at a cafe  \n\n")

    assert read_prompts(f) == ["a woman in a park", "a man at a cafe"]


def test_read_prompts_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        read_prompts(tmp_path / "nope.txt")


def test_read_prompts_empty_file_raises(tmp_path):
    f = tmp_path / "empty.txt"
    f.write_text("\n   \n\n")
    with pytest.raises(ValueError, match="no prompts"):
        read_prompts(f)


def test_slugify_is_stable_and_filesystem_safe():
    assert slugify("same person, sitting at a cafe!") == "same_person_sitting_at_a_cafe"
    assert slugify("A/B  test") == "a_b_test"


def test_slugify_truncates_and_never_empty():
    assert slugify("x" * 100, max_len=10) == "x" * 10
    assert slugify("!!!") == "prompt"  # fallback when nothing survives
