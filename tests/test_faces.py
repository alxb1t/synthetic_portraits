"""The FaceDetector facade: a Protocol + a scriptable fake.

Every generated image must contain exactly one antelopev2-detectable face (the consumer's
bar). Detection lives behind a `FaceDetector` Protocol so the regenerate loop is testable
offline: tests inject a `FakeFaceDetector` with scripted counts, so no unit test imports
insightface, downloads a model, or touches a GPU. The real antelopev2 implementation is
lazily imported (never at module load) so the runtime stays stdlib-only until it is used.
"""

from __future__ import annotations

from synthetic_portraits.faces import FaceDetector, FakeFaceDetector


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
