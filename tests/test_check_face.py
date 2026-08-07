"""Face-detectability check (Phase 6).

The real detector uses insightface/antelopev2 (heavy, offline on the host); these tests
inject a fake detector so the gate never imports insightface, downloads a model, or reads
a real image. They lock the assertion logic: every demo image must contain exactly one
detectable frontal face, or the consumer's identity stage would reject it.
"""

from __future__ import annotations

from pathlib import Path

import check_face


def _fake(counts: dict[str, int]):
    """A detector that returns a preset face count keyed by filename."""

    def detect(path: Path) -> int:
        return counts[Path(path).name]

    return detect


def test_exactly_one_face_passes():
    ok, n = check_face.check_image("a.png", detector=lambda _p: 1)
    assert ok is True
    assert n == 1


def test_zero_faces_fails():
    ok, n = check_face.check_image("a.png", detector=lambda _p: 0)
    assert ok is False
    assert n == 0


def test_multiple_faces_fails():
    ok, n = check_face.check_image("a.png", detector=lambda _p: 2)
    assert ok is False
    assert n == 2


def test_main_returns_zero_when_all_images_have_one_face(tmp_path, capsys):
    imgs = [tmp_path / "a.png", tmp_path / "b.png"]
    for p in imgs:
        p.write_bytes(b"x")
    det = _fake({"a.png": 1, "b.png": 1})
    rc = check_face.main([str(p) for p in imgs], detector=det)
    assert rc == 0


def test_main_returns_nonzero_when_any_image_fails(tmp_path):
    imgs = [tmp_path / "a.png", tmp_path / "b.png"]
    for p in imgs:
        p.write_bytes(b"x")
    det = _fake({"a.png": 1, "b.png": 2})  # b has two faces -> reject
    rc = check_face.main([str(p) for p in imgs], detector=det)
    assert rc == 1


def test_main_with_no_images_is_an_error():
    # Nothing to check is a usage error, not a silent pass.
    rc = check_face.main([], detector=lambda _p: 1)
    assert rc == 2
