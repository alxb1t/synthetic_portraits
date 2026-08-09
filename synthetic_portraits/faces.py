"""The FaceDetector facade — the pipeline's sanctioned non-stdlib seam.

Every generated image must contain exactly one antelopev2-detectable face (the consumer's
identity stage rejects zero-face or multi-face inputs). Detection is a *core, accepted*
dependency (insightface + CPU ``onnxruntime`` + antelopev2) but it lives behind a
:class:`FaceDetector` Protocol — like the :class:`~synthetic_portraits.transport.ComfyTransport`
seam — so it stays swappable and testable:

* Production injects :class:`AntelopeV2FaceDetector`, which lazily imports insightface/cv2
  the first time it is constructed. Merely importing this module pulls **nothing** heavy, so
  the runtime stays stdlib-only until the real detector is actually built.
* Tests inject :class:`FakeFaceDetector` (scripted counts), so no unit test imports
  insightface, downloads a model, or touches a GPU.

Adapted from ``scripts/check_face.py``; the facade takes image **bytes** (what the pipeline
holds in memory) rather than a path.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from typing import Protocol, runtime_checkable

__all__ = [
    "AntelopeV2FaceDetector",
    "FaceDetector",
    "FakeFaceDetector",
    "default_face_detector",
]


@runtime_checkable
class FaceDetector(Protocol):
    """Count the antelopev2-detectable faces in an encoded image."""

    def count_faces(self, image: bytes) -> int:
        """Return the number of detectable faces in the PNG/JPEG ``image`` bytes."""
        ...


class FakeFaceDetector:
    """Scriptable detector for tests: returns preset counts in sequence.

    The regenerate loop calls ``count_faces`` once per attempt; a script like ``[0, 2, 1]``
    drives "two failures then a one-face success". Once the script is exhausted it clamps to
    the last value (so an over-budget loop keeps failing/succeeding as written, never raising).
    """

    def __init__(self, counts: Sequence[int]):
        self._counts = list(counts)
        self.calls = 0

    def count_faces(self, image: bytes) -> int:
        index = self.calls
        self.calls += 1
        if not self._counts:
            return 0
        if index < len(self._counts):
            return self._counts[index]
        return self._counts[-1]


class AntelopeV2FaceDetector:
    """The real detector: insightface/antelopev2 on CPU ``onnxruntime`` (0 VRAM).

    Heavy deps are imported lazily in ``__init__`` so importing this module never pulls
    insightface/cv2 — the runtime stays stdlib-only until the detector is constructed.
    """

    def __init__(self, *, det_size: tuple[int, int] = (640, 640)):
        import cv2  # ty: ignore[unresolved-import]
        import numpy as np  # ty: ignore[unresolved-import]
        from insightface.app import FaceAnalysis  # ty: ignore[unresolved-import]

        _flatten_antelopev2_pack()
        app = FaceAnalysis(name="antelopev2", providers=["CPUExecutionProvider"])
        app.prepare(ctx_id=-1, det_size=det_size)
        self._app = app
        self._cv2 = cv2
        self._np = np

    def count_faces(self, image: bytes) -> int:
        buffer = self._np.frombuffer(image, dtype=self._np.uint8)
        decoded = self._cv2.imdecode(buffer, self._cv2.IMREAD_COLOR)
        if decoded is None:
            raise ValueError("could not decode image bytes for face detection")
        return len(self._app.get(decoded))


def default_face_detector() -> FaceDetector:
    """Construct the production antelopev2 detector (imports insightface lazily)."""
    return AntelopeV2FaceDetector()


def _flatten_antelopev2_pack() -> None:
    """Work around insightface's antelopev2 download bug: the zip extracts to a nested
    ``antelopev2/antelopev2/*.onnx`` folder, so FaceAnalysis can't find the models. Move any
    nested ``.onnx`` up one level. Mirrors the fix in ``scripts/check_face.py``."""
    root = Path.home() / ".insightface" / "models" / "antelopev2"
    nested = root / "antelopev2"
    if nested.is_dir():
        for onnx in nested.glob("*.onnx"):
            target = root / onnx.name
            if not target.exists():
                onnx.rename(target)
        if not any(nested.iterdir()):
            nested.rmdir()
