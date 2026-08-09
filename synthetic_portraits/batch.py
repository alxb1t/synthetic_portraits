"""Batch orchestration helpers for ``--prompts``: parse a prompt list + stable slugs.

``--prompts <file>`` runs the selected path (default or ``--identity``) **once per line**
through the regenerate loop, writing a **labeled set** (one stable-named file per prompt).
These are the pure pieces; the loop itself lives in the CLI over ``pipeline.run``.
"""

from __future__ import annotations

import re
from pathlib import Path

__all__ = ["read_prompts", "slugify"]

_SLUG_UNSAFE = re.compile(r"[^a-z0-9]+")


def read_prompts(path: str | Path) -> list[str]:
    """Read one prompt per line, dropping blank lines.

    Raises :class:`FileNotFoundError` if the file is missing and :class:`ValueError` if it
    holds no non-empty lines — an empty batch is a usage error, not a silent no-op.
    """
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"--prompts file not found: {path}")
    prompts = [line.strip() for line in p.read_text().splitlines() if line.strip()]
    if not prompts:
        raise ValueError(f"no prompts in {path}")
    return prompts


def slugify(text: str, *, max_len: int = 30) -> str:
    """A filesystem-safe, stable slug for a prompt (lowercase, ``_``-joined, truncated)."""
    slug = _SLUG_UNSAFE.sub("_", text.lower()).strip("_")[:max_len].strip("_")
    return slug or "prompt"
