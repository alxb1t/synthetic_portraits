"""The rented GPU: one session through gpunit, the `.env` it is handed, and its faults.

`gpunit` is imported inside the functions, never at module scope, so importing the CLI
imports no third-party package (0006 design D2).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any

# What `gpunit.session` takes and yields, as `generate.py --pod` calls it.
OpenSession = Callable[
    [Path, Mapping[str, str], Callable[[str], None]], AbstractContextManager[Any]
]

# The exit for a create whose answer was lost: a pod may exist that no record names.
LOST_EXIT = 3

# gpunit's CLI reads no `.env`, where the key lives, so each remedy loads it.
_DOWN = "uv run --env-file .env gpunit down"
_STATUS = "uv run --env-file .env gpunit status"


def read_env(path: Path) -> dict[str, str]:
    """Return a `.env` file's `KEY=VALUE` lines, quotes stripped; none if it is absent.

    e.g. `KEY="k"` -> {"KEY": "k"}
    """
    if not path.is_file():
        return {}
    pairs = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        text = line.strip()
        if not text or text.startswith("#") or "=" not in text:
            continue
        key, value = text.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        pairs[key.strip()] = value
    return pairs


def open_session(
    root: Path, environ: Mapping[str, str], say: Callable[[str], None]
) -> AbstractContextManager[Any]:
    """Return gpunit's session on `root`'s `gpunit.toml`, its lines sent to `say`."""
    import gpunit

    return gpunit.session(root / "gpunit.toml", environ=environ, cwd=root, say=say)


def fault_exit(fault: Exception) -> tuple[int, str | None] | None:
    """Return the exit code and the line to print for one of gpunit's faults; None otherwise.

    e.g. gpunit.Lost() -> (3, "refused: the provider's answer was lost; ...")
    """
    import gpunit

    if isinstance(fault, gpunit.Lost):
        return LOST_EXIT, (
            f"refused: the provider's answer was lost; `{_STATUS}` shows what is left, "
            f"and `{_DOWN}` deletes it"
        )
    if isinstance(fault, gpunit.TeardownFailed):
        return (
            1,
            f"refused: the session's teardown failed, and its pod may still bill; run `{_DOWN}`",
        )
    if isinstance(fault, gpunit.Refused):
        # gpunit has written its own `refused:` line through `say`.
        return 1, None
    return None
