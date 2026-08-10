"""The FaceDetector facade: a Protocol + a scriptable fake.

Every generated image must contain exactly one antelopev2-detectable face (the consumer's
bar). Detection lives behind a `FaceDetector` Protocol so the regenerate loop is testable
offline: tests inject a `FakeFaceDetector` with scripted counts, so no unit test imports
insightface, downloads a model, or touches a GPU. The real antelopev2 implementation is
lazily imported (never at module load) so the runtime stays stdlib-only until it is used.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest

from synthetic_portraits.faces import (
    _ANTELOPEV2_BASE,
    _ANTELOPEV2_REV,
    _ANTELOPEV2_SHA256,
    FaceDetector,
    FakeFaceDetector,
    ensure_antelopev2,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
DOWNLOAD_SH = REPO_ROOT / "download_models.sh"


def test_fake_is_a_face_detector():
    assert isinstance(FakeFaceDetector([1]), FaceDetector)


def test_fake_returns_scripted_counts_in_sequence():
    det = FakeFaceDetector([0, 2, 1])
    assert [det.count_faces(b"x") for _ in range(3)] == [0, 2, 1]


def test_fake_clamps_to_last_count_when_exhausted():
    det = FakeFaceDetector([1])
    assert det.count_faces(b"x") == 1
    assert det.count_faces(b"x") == 1  # clamped — no IndexError past the script
    assert det.calls == 2


def test_importing_faces_does_not_import_insightface():
    # The runtime stays stdlib-only until the real detector is constructed; merely
    # importing the module (Protocol + fake) must not pull the heavy optional deps.
    import sys

    import synthetic_portraits.faces  # noqa: F401

    assert "insightface" not in sys.modules
    assert "cv2" not in sys.modules


# --- security S3: stage the pinned + verified antelopev2 pack on the dev host ---------
#
# The offline face gate builds FaceAnalysis(name="antelopev2") with the models missing, so
# insightface auto-downloads the pack to ~/.insightface — unpinned, unverified. ensure_antelopev2
# stages the SAME pinned + SHA-256-verified files download_models.sh uses (single set of pins,
# asserted in sync below) so insightface finds them and never auto-fetches.

EXPECTED_ANTELOPEV2_FILES = {
    "1k3d68.onnx",
    "2d106det.onnx",
    "genderage.onnx",
    "glintr100.onnx",
    "scrfd_10g_bnkps.onnx",
}


def test_antelopev2_pins_are_wellformed():
    assert re.fullmatch(r"[0-9a-f]{40}", _ANTELOPEV2_REV)
    assert _ANTELOPEV2_REV in _ANTELOPEV2_BASE
    assert set(_ANTELOPEV2_SHA256) == EXPECTED_ANTELOPEV2_FILES
    for digest in _ANTELOPEV2_SHA256.values():
        assert re.fullmatch(r"[0-9a-f]{64}", digest)


def test_antelopev2_pins_match_download_models_sh():
    # Single source of truth: the host stager must use the exact rev + digests the pod
    # download script already pins (S1), so the two can never drift to different bytes.
    text = DOWNLOAD_SH.read_text()
    (rev,) = re.findall(r'^ANTELOPE_REV="?([0-9a-f]{40})"?', text, re.MULTILINE)
    assert rev == _ANTELOPEV2_REV
    files_match = re.search(r"ANTELOPE_FILES=\(([^)]*)\)", text)
    assert files_match
    files = files_match.group(1).split()
    shas = re.findall(r"^\s*([0-9a-f]{64})\s+#\s*(\S+)", text, re.MULTILINE)
    sh_map = {name: sha for sha, name in shas}
    assert set(files) == EXPECTED_ANTELOPEV2_FILES
    assert sh_map == _ANTELOPEV2_SHA256


class _FakeFetch:
    """A fetcher that writes preset bytes for each file name, recording what it fetched."""

    def __init__(self, payloads: dict[str, bytes]):
        self._payloads = payloads
        self.calls: list[str] = []

    def __call__(self, url: str, dest: Path) -> None:
        self.calls.append(url)
        dest.write_bytes(self._payloads[Path(url).name])


def test_ensure_antelopev2_downloads_and_verifies(tmp_path):
    payloads = {name: name.encode() for name in EXPECTED_ANTELOPEV2_FILES}
    digests = {name: hashlib.sha256(b).hexdigest() for name, b in payloads.items()}
    fetch = _FakeFetch(payloads)

    root = ensure_antelopev2(tmp_path, fetch=fetch, digests=digests, base_url="http://x")

    assert root == tmp_path
    for name in EXPECTED_ANTELOPEV2_FILES:
        assert (tmp_path / name).read_bytes() == payloads[name]
        assert not (tmp_path / f"{name}.partial").exists()  # temp file cleaned up
    assert len(fetch.calls) == len(EXPECTED_ANTELOPEV2_FILES)


def test_ensure_antelopev2_is_idempotent(tmp_path):
    payloads = {name: name.encode() for name in EXPECTED_ANTELOPEV2_FILES}
    digests = {name: hashlib.sha256(b).hexdigest() for name, b in payloads.items()}
    for name, b in payloads.items():
        (tmp_path / name).write_bytes(b)

    def boom(url: str, dest: Path) -> None:  # must never be called — files already valid
        raise AssertionError(f"unexpected fetch: {url}")

    ensure_antelopev2(tmp_path, fetch=boom, digests=digests, base_url="http://x")


def test_ensure_antelopev2_aborts_on_checksum_mismatch(tmp_path):
    payloads = {name: name.encode() for name in EXPECTED_ANTELOPEV2_FILES}
    # Expected digest for one file is wrong → a tampered/corrupt fetch must abort, unverified.
    digests = {name: hashlib.sha256(b).hexdigest() for name, b in payloads.items()}
    bad = "2d106det.onnx"
    digests[bad] = "0" * 64

    fetch = _FakeFetch(payloads)
    with pytest.raises(RuntimeError, match="SHA-256"):
        ensure_antelopev2(tmp_path, fetch=fetch, digests=digests, base_url="http://x")

    assert not (tmp_path / bad).exists()  # nothing half-verified is left behind
    assert not (tmp_path / f"{bad}.partial").exists()
