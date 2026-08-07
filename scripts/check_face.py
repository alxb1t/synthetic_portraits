"""Offline antelopev2 face-detectability check (dev-only).

Every demo image the pipeline ships to the consumer must contain **exactly one** clear,
frontal face — the consumer's identity stage runs InsightFace/antelopev2 on it, and
rejects zero-face or multi-face inputs. This script asserts that on every given image.

It runs on the host, not on the pod: it uses the ``insightface`` package (CPU
``onnxruntime``), which auto-downloads the antelopev2 model pack on first run. Install the
optional deps with ``uv sync --group faces`` first, then:

    uv run --group faces scripts/check_face.py examples/*.png

The detector is injectable so the unit tests exercise the pass/fail logic without
insightface, a model download, or a real image.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from pathlib import Path

# A detector maps an image path to the number of detectable faces in it.
Detector = Callable[[Path], int]


def _flatten_antelopev2_pack() -> None:
    """Work around insightface's antelopev2 download bug: the zip extracts to a nested
    ``antelopev2/antelopev2/*.onnx`` folder, so FaceAnalysis can't find the models
    (``AssertionError: 'detection' in self.models``). Move any nested .onnx up one level."""
    root = Path.home() / ".insightface" / "models" / "antelopev2"
    nested = root / "antelopev2"
    if nested.is_dir():
        for onnx in nested.glob("*.onnx"):
            target = root / onnx.name
            if not target.exists():
                onnx.rename(target)
        if not any(nested.iterdir()):
            nested.rmdir()


def _antelopev2_detector() -> Detector:
    """Build the real insightface/antelopev2 detector (CPU). Imported lazily so the
    gate and tests never need insightface installed."""
    import cv2  # ty: ignore[unresolved-import]
    from insightface.app import FaceAnalysis  # ty: ignore[unresolved-import]

    _flatten_antelopev2_pack()
    app = FaceAnalysis(name="antelopev2", providers=["CPUExecutionProvider"])
    app.prepare(ctx_id=-1, det_size=(640, 640))

    def detect(path: Path) -> int:
        image = cv2.imread(str(path))
        if image is None:
            raise ValueError(f"could not read image: {path}")
        return len(app.get(image))

    return detect


def check_image(path: str | Path, *, detector: Detector) -> tuple[bool, int]:
    """Return ``(ok, n_faces)`` — ok is True iff exactly one face is detected."""
    n = detector(Path(path))
    return n == 1, n


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="check_face.py",
        description="Assert every image has exactly one antelopev2-detectable frontal face.",
    )
    parser.add_argument("images", nargs="*", help="Image files to check.")
    return parser


def main(argv: Sequence[str] | None = None, *, detector: Detector | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.images:
        print("no images given", flush=True)
        return 2

    det = detector if detector is not None else _antelopev2_detector()
    failures = 0
    for image in args.images:
        ok, n = check_image(image, detector=det)
        status = "OK" if ok else "FAIL"
        print(f"[{status}] {image}: {n} face(s)", flush=True)
        if not ok:
            failures += 1

    total = len(args.images)
    print(f"{total - failures}/{total} images have exactly one detectable face", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
