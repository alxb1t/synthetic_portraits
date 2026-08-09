"""CLI entry point: parse flags, build a request, dispatch a model, render.

The transport is injectable so tests drive ``main`` against a ``FakeComfyClient`` (no GPU,
no network). Pose is prompt-driven — described in ``--prompt``, no reference image.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from . import pipeline
from .faces import FaceDetector, default_face_detector
from .models import DEFAULT_MODEL, IDENTITY_MODEL, MODELS, get_model
from .transport import ComfyClient, ComfyTransport
from .workflow import (
    DEFAULT_HEIGHT,
    DEFAULT_NEGATIVE,
    DEFAULT_WIDTH,
    GenerationRequest,
    NamedInput,
)

DEFAULT_SERVER = os.environ.get("COMFY_URL", "http://127.0.0.1:8188")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="generate.py",
        description="Generate a photoreal upper-body image of a person who does not exist.",
    )
    parser.add_argument("--prompt", help="Text prompt describing the synthetic person.")
    parser.add_argument(
        "--identity",
        help="Reference face (hero) image; produces that same person via InstantID.",
    )
    parser.add_argument(
        "--model", default=DEFAULT_MODEL, choices=sorted(MODELS), help="Registered model to use."
    )
    parser.add_argument("--negative", default=DEFAULT_NEGATIVE, help="Negative prompt.")
    parser.add_argument("--width", type=int, default=DEFAULT_WIDTH, help="Latent width.")
    parser.add_argument("--height", type=int, default=DEFAULT_HEIGHT, help="Latent height.")
    parser.add_argument("--seed", type=int, default=0, help="Sampler seed (reproducibility).")
    parser.add_argument(
        "-n",
        "--count",
        type=int,
        default=1,
        help="Number of images to render (consecutive seeds from --seed).",
    )
    parser.add_argument("--out", "-o", default="outputs", help="Directory for rendered images.")
    parser.add_argument("--server", default=DEFAULT_SERVER, help="ComfyUI server URL.")
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    transport: ComfyTransport | None = None,
    detector: FaceDetector | None = None,
) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.prompt:
        parser.print_help()
        return 0

    # --identity supplies a hero -> auto-select the InstantID graph and upload the hero as a
    # named input. Without it, stay on the hardened default graph with zero inputs.
    inputs: tuple[NamedInput, ...] = ()
    if args.identity:
        hero_path = Path(args.identity)
        if not hero_path.is_file():
            parser.error(f"--identity file not found: {args.identity}")
        inputs = (
            NamedInput(role="identity", filename=hero_path.name, data=hero_path.read_bytes()),
        )
        model = get_model(IDENTITY_MODEL)
    else:
        model = get_model(args.model)

    client = transport if transport is not None else ComfyClient(args.server)
    face_detector = detector if detector is not None else default_face_detector()

    saved = []
    failures = 0
    total = 0
    for offset in range(max(1, args.count)):
        req = GenerationRequest(
            prompt=args.prompt,
            negative=args.negative,
            width=args.width,
            height=args.height,
            seed=args.seed + offset,
            inputs=inputs,
        )
        outcome = pipeline.run(client, model, req, out_dir=args.out, detector=face_detector)
        saved.extend(outcome.paths)
        total += 1
        if not outcome.detected:
            failures += 1
            print(
                f"WARNING: no single antelopev2 face after {outcome.attempts} attempts "
                f"(seed {req.seed}) — kept last render",
                file=sys.stderr,
            )

    for path in saved:
        print(path)

    if failures:
        print(
            f"{failures}/{total} images failed face detection (kept, but undetected)",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
