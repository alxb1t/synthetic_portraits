"""The pod's provisioner: the model manifest's pins, and `fetch` landing them verified."""

from __future__ import annotations

import hashlib
import io
import json
import re
from contextlib import contextmanager
from pathlib import Path

import pytest
from conftest import REPO_ROOT

from synthetic_portraits import provision

MANIFEST = REPO_ROOT / "config" / "models.json"


def _entries() -> list[dict[str, str]]:
    return json.loads(MANIFEST.read_text())["entries"]


class _FakeUrlopen:
    """Serve preset bytes per URL, recording each URL asked for."""

    def __init__(self, payloads: dict[str, bytes]):
        self.payloads = payloads
        self.asked: list[str] = []

    @contextmanager
    def __call__(self, url: str, timeout: float):
        self.asked.append(url)
        yield io.BytesIO(self.payloads[url])


def _manifest(tmp_path: Path, files: dict[str, bytes], *, wrong: str | None = None) -> Path:
    """Write a manifest of `dest -> bytes`, each pinned by its digest; `wrong` pins a bad one."""
    entries = [
        {
            "dest": dest,
            "source": f"https://example.org/resolve/{'a' * 40}/{dest}",
            "sha256": "0" * 64 if dest == wrong else hashlib.sha256(data).hexdigest(),
        }
        for dest, data in files.items()
    ]
    path = tmp_path / "models.json"
    path.write_text(json.dumps({"entries": entries}))
    return path


def _served(files: dict[str, bytes]) -> _FakeUrlopen:
    return _FakeUrlopen(
        {f"https://example.org/resolve/{'a' * 40}/{dest}": data for dest, data in files.items()}
    )


FILES = {
    "checkpoints/model.safetensors": b"weights",
    "insightface/models/antelopev2/scrfd.onnx": b"detector",
}


@pytest.mark.spec("pod.download-idempotent")
def test_the_manifest_covers_every_model_the_pipeline_needs():
    dests = {entry["dest"] for entry in _entries()}

    assert {
        "checkpoints/RealVisXL_V5.0_fp16.safetensors",
        "instantid/ip-adapter.bin",
        "controlnet/diffusion_pytorch_model.safetensors",
        "controlnet/config.json",
        "ultralytics/bbox/face_yolov8m.pt",
    } <= dests
    assert {
        f"insightface/models/antelopev2/{name}"
        for name in (
            "1k3d68.onnx",
            "2d106det.onnx",
            "genderage.onnx",
            "glintr100.onnx",
            "scrfd_10g_bnkps.onnx",
        )
    } <= dests


@pytest.mark.spec("pod.download-idempotent")
def test_a_volume_that_holds_the_models_fetches_nothing(tmp_path):
    manifest = _manifest(tmp_path, FILES)
    models = tmp_path / "models"
    first = _served(FILES)
    assert provision.fetch(manifest, models, opener=first) == 0
    assert len(first.asked) == len(FILES)

    again = _served(FILES)

    assert provision.fetch(manifest, models, opener=again) == 0
    assert again.asked == []


@pytest.mark.spec("pod.download-idempotent")
def test_a_present_file_that_does_not_verify_is_fetched_again(tmp_path):
    manifest = _manifest(tmp_path, FILES)
    models = tmp_path / "models"
    swapped = models / "checkpoints" / "model.safetensors"
    swapped.parent.mkdir(parents=True)
    swapped.write_bytes(b"swapped out of band")
    served = _served(FILES)

    assert provision.fetch(manifest, models, opener=served) == 0

    assert swapped.read_bytes() == b"weights"


@pytest.mark.spec("pod.download-isolates")
def test_each_model_lands_under_the_directory_its_consumer_reads(tmp_path):
    manifest = _manifest(tmp_path, FILES)
    models = tmp_path / "models"

    provision.fetch(manifest, models, opener=_served(FILES))

    assert (models / "checkpoints" / "model.safetensors").read_bytes() == b"weights"
    assert (models / "insightface/models/antelopev2/scrfd.onnx").read_bytes() == b"detector"


@pytest.mark.spec("pod.download-isolates")
def test_every_manifest_entry_names_its_consumers_directory():
    roots = {"checkpoints", "instantid", "controlnet", "insightface", "ultralytics"}
    for entry in _entries():
        dest = Path(entry["dest"])
        assert not dest.is_absolute() and ".." not in dest.parts, entry["dest"]
        assert dest.parts[0] in roots and len(dest.parts) >= 2, entry["dest"]


@pytest.mark.spec("pod.download-isolates")
def test_a_destination_outside_the_models_directory_is_refused(tmp_path):
    manifest = _manifest(tmp_path, {"../escape.bin": b"x"})

    assert provision.fetch(manifest, tmp_path / "models", opener=_served({})) == 1
    assert not (tmp_path / "escape.bin").exists()


def _unpinned(sources: list[str]) -> list[str]:
    """Return each source not addressed by a 40-hex commit revision."""
    return [s for s in sources if not re.search(r"/resolve/[0-9a-f]{40}/", s)]


@pytest.mark.spec("pod.download-pins-revisions")
def test_every_source_is_pinned_to_an_immutable_commit_revision():
    assert _unpinned([entry["source"] for entry in _entries()]) == []


@pytest.mark.spec_exempt("structural: twin of the manifest's revision check")
def test_the_revision_check_catches_a_branch_and_a_tag():
    assert _unpinned(
        [
            "https://huggingface.co/a/b/resolve/main/m.bin",
            "https://huggingface.co/a/b/resolve/v1.0/m.bin",
            f"https://huggingface.co/a/b/resolve/{'c' * 40}/m.bin",
        ]
    ) == [
        "https://huggingface.co/a/b/resolve/main/m.bin",
        "https://huggingface.co/a/b/resolve/v1.0/m.bin",
    ]


@pytest.mark.spec("pod.download-verifies-sha256")
def test_every_manifest_entry_records_a_digest():
    for entry in _entries():
        assert re.fullmatch(r"[0-9a-f]{64}", entry["sha256"]), entry["dest"]


@pytest.mark.spec("pod.download-verifies-sha256")
def test_a_digest_mismatch_aborts_naming_both_digests_and_lands_nothing(tmp_path, capsys):
    dest = "checkpoints/model.safetensors"
    manifest = _manifest(tmp_path, FILES, wrong=dest)
    models = tmp_path / "models"

    assert provision.fetch(manifest, models, opener=_served(FILES)) == 1

    err = capsys.readouterr().err
    assert "0" * 64 in err
    assert hashlib.sha256(b"weights").hexdigest() in err
    assert not (models / dest).exists()
    assert not (models / f"{dest}.partial").exists()


@pytest.mark.spec("pod.download-verifies-sha256")
def test_the_command_line_fetches_into_the_named_directory(tmp_path, monkeypatch):
    manifest = _manifest(tmp_path, FILES)
    models = tmp_path / "models"
    monkeypatch.setattr(provision, "urlopen", _served(FILES))

    rc = provision.main(["fetch", "--models-dir", str(models), "--manifest", str(manifest)])

    assert rc == 0
    assert (models / "checkpoints" / "model.safetensors").read_bytes() == b"weights"
