"""Land every model the manifest pins onto the volume, each SHA-256 verified.

    python3 provision.py fetch [--models-dir DIR] [--manifest PATH]

A present file whose digest matches is skipped; the rest are fetched to `.partial`,
verified, and renamed, so a file under its final name is always a verified one.

Stdlib only and run as a file on the image's Python 3.10: the image holds this module
beside `pod_start.py`, not the package (0006 design D5, D6).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.request import urlopen

HERE = Path(__file__).resolve().parent

# The image copies the manifest beside this file.
MANIFEST = HERE / "models.json"

CHUNK = 1024 * 1024
TIMEOUT_S = 60.0


@dataclass(frozen=True)
class Entry:
    """One pinned file: where it lands under the models directory, where from, its digest."""

    dest: str
    source: str
    sha256: str


def load(manifest: Path) -> list[Entry]:
    """Return the manifest's entries, in order."""
    raw = json.loads(manifest.read_text(encoding="utf-8"))
    return [Entry(e["dest"], e["source"], e["sha256"]) for e in raw["entries"]]


def digest(path: Path) -> str:
    """Return a file's SHA-256, read in chunks."""
    hashed = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(CHUNK), b""):
            hashed.update(chunk)
    return hashed.hexdigest()


def target(models_dir: Path, entry: Entry) -> Path:
    """Return where `entry` lands; raise `ValueError` if that is outside `models_dir`."""
    root = models_dir.resolve()
    path = (root / entry.dest).resolve()
    if root not in path.parents:
        raise ValueError(f"{entry.dest} lands outside {models_dir}")
    return path


def transfer(entry: Entry, dest: Path, opener: Callable[..., Any]) -> str:
    """Stream `entry`'s source into `dest`; return the SHA-256 of what was written."""
    hashed = hashlib.sha256()
    with opener(entry.source, timeout=TIMEOUT_S) as answer, dest.open("wb") as out:
        for chunk in iter(lambda: answer.read(CHUNK), b""):
            hashed.update(chunk)
            out.write(chunk)
    return hashed.hexdigest()


def fetch(manifest: Path, models_dir: Path, *, opener: Callable[..., Any] | None = None) -> int:
    """Land every entry of `manifest` under `models_dir`, verified; return the exit code.

    0 every file is in place · 1 a destination escapes, or a digest does not match.
    """
    # Read at call time, so a test can replace the module's `urlopen`.
    opener = opener if opener is not None else urlopen
    for entry in load(manifest):
        try:
            final = target(models_dir, entry)
        except ValueError as escaped:
            print(f"ERROR: {escaped}", file=sys.stderr)
            return 1
        if final.is_file() and digest(final) == entry.sha256:
            print(f"skip (present, verified): {entry.dest}", flush=True)
            continue
        final.parent.mkdir(parents=True, exist_ok=True)
        partial = final.with_name(final.name + ".partial")
        print(f"fetching: {entry.source}", flush=True)
        try:
            got = transfer(entry, partial, opener)
        except BaseException:
            partial.unlink(missing_ok=True)
            raise
        if got != entry.sha256:
            partial.unlink()
            print(
                f"ERROR: SHA-256 mismatch for {entry.dest}: expected {entry.sha256}, got {got}",
                file=sys.stderr,
            )
            return 1
        os.replace(partial, final)
        print(f"saved (verified): {entry.dest}", flush=True)
    print(f"models ready under {models_dir}", flush=True)
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Parse `fetch`'s flags and run it; return its exit code."""
    parser = argparse.ArgumentParser(prog="provision.py")
    verbs = parser.add_subparsers(dest="verb", required=True)
    run = verbs.add_parser("fetch", help="Land and verify every model the manifest pins.")
    run.add_argument("--models-dir", type=Path, help="Default: $GPUNIT_VOLUME_PATH/models.")
    run.add_argument("--manifest", type=Path, default=MANIFEST)
    args = parser.parse_args(argv)
    models_dir = args.models_dir
    if models_dir is None:
        volume = os.environ.get("GPUNIT_VOLUME_PATH", "")
        if not volume:
            parser.error("--models-dir is required when GPUNIT_VOLUME_PATH is unset")
        models_dir = Path(volume) / "models"
    return fetch(args.manifest, models_dir)


if __name__ == "__main__":
    sys.exit(main())
