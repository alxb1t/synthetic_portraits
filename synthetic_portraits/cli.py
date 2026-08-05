"""CLI entry point.

Phase 1 stands up the bare skeleton (arg parsing only). The real dispatch, injection,
and rendering flags (``--model``, ``--pose-image``, ``--width``/``--height``, ``--seed``,
``-n``) land in Phases 2 and 4.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence

# Default portrait aspect for upper-body framing (the EmptyLatentImage dims).
DEFAULT_WIDTH = 832
DEFAULT_HEIGHT = 1216


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="generate.py",
        description="Generate a photoreal upper-body image of a person who does not exist.",
    )
    parser.add_argument("--prompt", help="Text prompt describing the synthetic person.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.prompt:
        parser.print_help()
        return 0

    # Rendering is wired up in later phases.
    raise SystemExit("generation is not implemented yet (Phase 1 skeleton)")


if __name__ == "__main__":
    raise SystemExit(main())
