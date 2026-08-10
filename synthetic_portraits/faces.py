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

import hashlib
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Protocol, runtime_checkable

__all__ = [
    "AntelopeV2FaceDetector",
    "FaceDetector",
    "FakeFaceDetector",
    "default_face_detector",
    "ensure_antelopev2",
]

# --- antelopev2 pins (security S1/S3) -------------------------------------------------
# The pod fetches this pack via download_models.sh (pinned commit SHA + SHA-256 verified).
# On the dev **host**, insightface's FaceAnalysis(name="antelopev2") would otherwise
# auto-download the pack to ~/.insightface unpinned + unverified — so ensure_antelopev2()
# stages the SAME files (identical rev + digests, kept in sync with download_models.sh by
# tests/test_faces.py) before the detector is built. Third-party mirror → pin + checksum.
_ANTELOPEV2_REV = "397cafa6d8310e96e302e96528c20a4c92a884f2"
_ANTELOPEV2_BASE = (
    "https://huggingface.co/MonsterMMORPG/InstantID_Models/"
    f"resolve/{_ANTELOPEV2_REV}/models/antelopev2"
)
_ANTELOPEV2_SHA256 = {
    "1k3d68.onnx": "df5c06b8a0c12e422b2ed8947b8869faa4105387f199c477af038aa01f9a45cc",
    "2d106det.onnx": "f001b856447c413801ef5c42091ed0cd516fcd21f2d6b79635b1e733a7109dbf",
    "genderage.onnx": "4fde69b1c810857b88c64a335084f1c3fe8f01246c9a191b48c7bb756d6652fb",
    "glintr100.onnx": "4ab1d6435d639628a6f3e5008dd4f929edf4c4124b1a7169e1048f9fef534cdf",
    "scrfd_10g_bnkps.onnx": "5838f7fe053675b1c7a08b633df49e7af5495cee0493c7dcf6697200b85b5b91",
}

Fetcher = Callable[[str, Path], None]


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

        ensure_antelopev2()
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


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _urlretrieve(url: str, dest: Path) -> None:
    with urllib.request.urlopen(url) as response, dest.open("wb") as handle:
        while chunk := response.read(1 << 20):
            handle.write(chunk)


def ensure_antelopev2(
    root: Path | None = None,
    *,
    fetch: Fetcher = _urlretrieve,
    digests: Mapping[str, str] = _ANTELOPEV2_SHA256,
    base_url: str = _ANTELOPEV2_BASE,
) -> Path:
    """Stage the pinned + SHA-256-verified antelopev2 pack so the dev-host face gate never
    lets insightface auto-download it unpinned + unverified (security S3).

    Idempotent: a file already present with the expected digest is left in place. Each file
    is fetched to a ``.partial`` and verified **before** it lands under its real name, so a
    tampered or interrupted download is never trusted (mismatch → remove + abort). Returns
    the antelopev2 model directory (default ``~/.insightface/models/antelopev2``).
    """
    root = root or (Path.home() / ".insightface" / "models" / "antelopev2")
    root.mkdir(parents=True, exist_ok=True)
    for name, expected in digests.items():
        dest = root / name
        if dest.exists() and _sha256_file(dest) == expected:
            continue
        partial = root / f"{name}.partial"
        fetch(f"{base_url}/{name}", partial)
        actual = _sha256_file(partial)
        if actual != expected:
            partial.unlink(missing_ok=True)
            raise RuntimeError(
                f"SHA-256 mismatch for antelopev2/{name}: expected {expected}, got {actual}"
            )
        partial.replace(dest)
    return root
