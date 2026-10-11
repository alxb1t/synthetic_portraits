"""The rented GPU: one session through gpunit, the `.env` it is handed, and its faults.

`gpunit` is imported inside the functions, never at module scope, so importing the CLI
imports no third-party package (0006 design D2).
"""

from __future__ import annotations

import shlex
import signal
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


def _remedy(command: str, root: Path) -> str:
    """Return the gpunit command that acts on `root`'s session, run from `root`.

    gpunit's CLI reads no `.env`, where the key lives, so the remedy loads it through uv.
    uv lets a key the shell exports win over `.env`'s, the reverse of `--pod` (D2), so a
    shell holding another key must unset it first.
    e.g. ("down", Path("/r")) -> "cd /r && uv run --env-file .env gpunit down"
    """
    return f"cd {shlex.quote(str(root))} && uv run --env-file .env gpunit {command}"


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


def fault_exit(fault: BaseException, say: Callable[[str], None], root: Path) -> int | None:
    """Say why `root`'s session ended and return its exit code; None for a fault not gpunit's.

    e.g. gpunit.Lost() -> says "refused: the provider's answer was lost; ...", returns 3
    """
    import gpunit

    down = _remedy("down", root)

    if isinstance(fault, KeyboardInterrupt):
        # gpunit's `Interrupted` carries the signal; a bare Ctrl-C is SIGINT.
        return 128 + int(getattr(fault, "signal", signal.SIGINT))
    if isinstance(fault, gpunit.Lost):
        say(
            f"refused: the provider's answer was lost; `{_remedy('status', root)}` shows what "
            f"is left, and `{down}` deletes it"
        )
        return LOST_EXIT
    if isinstance(fault, gpunit.TeardownFailed):
        say(f"refused: the session's teardown failed, and its pod may still bill; run `{down}`")
        return 1
    if isinstance(fault, gpunit.Refused):
        # gpunit has written its own `refused:` line through `say`.
        return 1
    return None
