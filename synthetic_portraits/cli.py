"""CLI entry point: parse flags, build a request, dispatch a model, render.

The transport, the detector and the GPU session are injectable, so tests drive ``main``
against fakes (no GPU, no network). Pose is prompt-driven — described in ``--prompt``, no
reference image.
"""

from __future__ import annotations

import argparse
import http.client
import os
import random
import signal
import sys
import time
from collections.abc import Callable, Sequence
from pathlib import Path

from . import gpu, pipeline
from .batch import read_prompts, slugify
from .faces import (
    FACES_GROUP_HINT,
    FaceDetector,
    default_face_detector,
    missing_face_dependencies,
)
from .models import DEFAULT_MODEL, IDENTITY_MODEL, SELECTABLE_MODELS, Model, get_model
from .transport import ComfyClient, ComfyError, ComfyTransport, ReportingTransport
from .workflow import (
    DEFAULT_HEIGHT,
    DEFAULT_NEGATIVE,
    DEFAULT_WIDTH,
    GenerationRequest,
    NamedInput,
)

# Upper bound for a randomly chosen seed when --seed is omitted (ComfyUI seeds are 0..2^32-1).
_RANDOM_SEED_MAX = 2**31

DEFAULT_SERVER = os.environ.get("COMFY_URL", "http://127.0.0.1:8188")

# The repository whose `gpunit.toml` and `.env` a `--pod` session reads.
REPOSITORY = Path(__file__).resolve().parent.parent

# The render server's port on the pod, which `gpunit.toml` forwards; a test holds them equal.
POD_PORT = 8188

# A cold volume downloads its models before ComfyUI starts (0006 design D3).
WAIT_S = 900.0
POLL_S = 5.0

# What a tunnel with no server behind it answers: refused, reset, or cut mid-response.
_SILENT = (ComfyError, OSError, http.client.HTTPException)


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the ``generate.py`` command line."""
    parser = argparse.ArgumentParser(
        prog="generate.py",
        description="Generate a photoreal upper-body image of a person who does not exist.",
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--prompt", help="Text prompt describing the synthetic person.")
    source.add_argument(
        "--prompts",
        help="File of prompts, one per line — a batch (character sheet with --identity).",
    )
    parser.add_argument(
        "--identity",
        help="Reference face (hero) image; produces that same person via InstantID.",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        choices=SELECTABLE_MODELS,
        help="Registered model to use (the identity graph is auto-selected by --identity).",
    )
    parser.add_argument("--negative", default=DEFAULT_NEGATIVE, help="Negative prompt.")
    parser.add_argument("--width", type=int, default=DEFAULT_WIDTH, help="Latent width.")
    parser.add_argument("--height", type=int, default=DEFAULT_HEIGHT, help="Latent height.")
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Sampler seed (reproducibility). Omit for a random base seed.",
    )
    parser.add_argument(
        "-n",
        "--count",
        type=int,
        default=1,
        help="Number of images to render (consecutive seeds from --seed).",
    )
    parser.add_argument("--out", "-o", default="outputs", help="Directory for rendered images.")
    target = parser.add_mutually_exclusive_group()
    target.add_argument("--server", default=DEFAULT_SERVER, help="ComfyUI server URL.")
    target.add_argument(
        "--pod",
        action="store_true",
        help="Render on a rented GPU: one gpunit session from gpunit.toml, torn down at the end.",
    )
    return parser


def await_server(
    ask: Callable[[], object],
    *,
    wait_s: float = WAIT_S,
    poll_s: float = POLL_S,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> bool:
    """Return True once ``ask`` answers; False when it has not within ``wait_s`` seconds."""
    deadline = clock() + wait_s
    while True:
        try:
            ask()
            return True
        except _SILENT:
            if clock() >= deadline:
                return False
            sleep(poll_s)


def _on_pod(
    render: Callable[[ComfyTransport], int],
    open_session: gpu.OpenSession,
    connect: Callable[[str], ReportingTransport],
) -> int:
    """Render through one gpunit session, closed on every way out; return the exit code.

    The batch's code · 1 a refusal · 3 the create's answer was lost · 128+n a signal.
    """

    def say(line: str) -> None:
        print(line, file=sys.stderr)

    environ = {**os.environ, **gpu.read_env(REPOSITORY / ".env")}
    try:
        with open_session(REPOSITORY, environ, say) as session:
            print(f"session image: {session.image}", file=sys.stderr)
            client = connect(f"http://127.0.0.1:{session.port(POD_PORT)}")
            if not await_server(client.system_stats, wait_s=WAIT_S, poll_s=POLL_S):
                print(
                    f"refused: the render server did not answer within {WAIT_S:g}s",
                    file=sys.stderr,
                )
                return 1
            return render(client)
    except KeyboardInterrupt as stopped:
        # gpunit's `Interrupted` carries the signal; a bare Ctrl-C is SIGINT.
        return 128 + int(getattr(stopped, "signal", signal.SIGINT))
    except Exception as fault:
        ended = gpu.fault_exit(fault)
        if ended is None:
            raise
        code, line = ended
        if line is not None:
            print(line, file=sys.stderr)
        return code


def main(
    argv: Sequence[str] | None = None,
    *,
    transport: ComfyTransport | None = None,
    detector: FaceDetector | None = None,
    open_session: gpu.OpenSession = gpu.open_session,
    connect: Callable[[str], ReportingTransport] = ComfyClient,
) -> int:
    """Run one generation request from parsed arguments; return a process exit code.

    ``transport``, ``detector``, ``open_session`` and ``connect`` are the injected seams:
    the tests pass fakes, so no test reaches a GPU or the network. Left as defaults they
    resolve to the real ComfyUI client, the real antelopev2 detector and a gpunit session.
    """
    parser = build_parser()
    args = parser.parse_args(argv)

    # Exactly one prompt source. --prompts is a batch (one render per line); --prompt is a
    # single prompt; the two are mutually exclusive (argparse enforces it). Neither -> help.
    if args.prompts:
        try:
            prompts = read_prompts(args.prompts)
        except (FileNotFoundError, ValueError) as exc:
            parser.error(str(exc))
        labeled = True
    elif args.prompt:
        prompts = [args.prompt]
        labeled = False
    else:
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

    # The detector is built before anything is queued, so a missing optional dependency is
    # reported while it is still free to fix — the render server is a metered GPU pod, and
    # the bare ModuleNotFoundError used to surface only after it was already billing. The
    # check runs ONLY on the non-injected path, so a caller supplying a stand-in (every
    # test does) never needs the group at all. See change 0004, design D5.
    face_detector = detector
    if face_detector is None:
        missing = missing_face_dependencies()
        if missing:
            parser.error(f"{FACES_GROUP_HINT} (missing: {', '.join(missing)})")
        face_detector = default_face_detector()

    def render(client: ComfyTransport) -> int:
        return _render_batch(
            client, model, prompts, args, inputs=inputs, labeled=labeled, detector=face_detector
        )

    if args.pod:
        return _on_pod(render, open_session, connect)
    return render(transport if transport is not None else ComfyClient(args.server))


def _render_batch(
    client: ComfyTransport,
    model: Model,
    prompts: list[str],
    args: argparse.Namespace,
    *,
    inputs: tuple[NamedInput, ...],
    labeled: bool,
    detector: FaceDetector,
) -> int:
    """Render every prompt ``args.count`` times through ``client``; return the exit code."""
    # A fixed --seed reproduces the whole set; omit it for a random base. Every element of the
    # set (prompt i, render k) gets a distinct, consecutive seed off that base.
    base_seed = args.seed if args.seed is not None else random.randrange(_RANDOM_SEED_MAX)

    saved = []
    failures = 0
    total = 0
    element = 0
    for i, prompt in enumerate(prompts):
        for k in range(max(1, args.count)):
            label = f"{i:02d}_{k:02d}_{slugify(prompt)}" if labeled else None
            req = GenerationRequest(
                prompt=prompt,
                negative=args.negative,
                width=args.width,
                height=args.height,
                seed=base_seed + element,
                inputs=inputs,
            )
            element += 1
            outcome = pipeline.run(
                client, model, req, out_dir=args.out, detector=detector, label=label
            )
            saved.extend(outcome.paths)
            total += 1
            if not outcome.detected:
                failures += 1
                print(
                    f"WARNING: no single antelopev2 face after {outcome.attempts} attempts "
                    f"(seed {req.seed}, prompt {i}) — kept last render",
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
