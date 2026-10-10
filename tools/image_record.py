"""Print the build record: the SHA-256 of the `Dockerfile` and of every file it copies.

Run it from anywhere:

    python3 tools/image_record.py
    e.g. {"Dockerfile": "<sha256>", "config/models.json": "<sha256>", ...}

`config/image.json` holds the same object under `files`, and a test re-derives it;
`build-image.yml` prints it into the build's summary from its own checkout, so an image
says which tree it was built from (0006 design D9). Stdlib only: the workflow runs it
without installing the project.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# A `COPY` from the build context: one source, one destination, no flag. An
# instruction's name is case-insensitive and may follow whitespace.
COPY = re.compile(r"^\s*COPY\s+(?!--)(\S+)\s+(\S+)\s*$", re.I)

# The forms that take nothing from the build context: a `COPY` from another image,
# and an `ADD` of a URL whose checksum the `Dockerfile` itself pins.
FROM_IMAGE = re.compile(r"^\s*COPY\s+--from=", re.I)
CHECKSUMMED_URL = re.compile(
    r"^\s*ADD\s+--checksum=sha256:[0-9a-f]{64}\s+https://\S+\s+\S+\s*$", re.I
)
TAKES_FILES = re.compile(r"^\s*(COPY|ADD)\s", re.I)


def instructions(dockerfile: str) -> list[str]:
    r"""Return each instruction as written, its continued lines joined by newlines.

    A comment line inside a continuation is dropped, as Docker drops it.
    e.g. "RUN a \\\n  b\nCOPY c /c\n" -> ["RUN a \\\n  b", "COPY c /c"]
    """
    found: list[str] = []
    held: list[str] = []
    for line in dockerfile.splitlines():
        if held and line.lstrip().startswith("#"):
            continue
        held.append(line)
        if not line.rstrip().endswith("\\"):
            found.append("\n".join(held))
            held = []
    if held:
        found.append("\n".join(held))
    return found


def copied(dockerfile: str) -> list[str]:
    """Return each source a `COPY` takes from the build context, in order.

    Raise `ValueError` naming any other `COPY` or `ADD`, so no copied file leaves the
    record unseen. e.g. "COPY --chmod=755 a.py /a.py" -> ValueError
    """
    sources = []
    for written in instructions(dockerfile):
        if not TAKES_FILES.match(written):
            continue
        joined = " ".join(part.rstrip().removesuffix("\\") for part in written.split("\n"))
        if FROM_IMAGE.match(written) or CHECKSUMMED_URL.match(joined):
            continue
        found = COPY.match(written)
        if found is None or "\n" in written:
            raise ValueError(
                f"cannot read {written!r}: a COPY from the build context takes one source, "
                "one destination and no flag, and an ADD only a URL with --checksum"
            )
        sources.append(found[1])
    return sources


def record(root: Path = ROOT) -> dict[str, str]:
    """Return the SHA-256 of `root`'s `Dockerfile` and each file it copies, by path."""
    names = ["Dockerfile", *copied((root / "Dockerfile").read_text(encoding="utf-8"))]
    return {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in names}


if __name__ == "__main__":
    print(json.dumps(record(), indent=2))
