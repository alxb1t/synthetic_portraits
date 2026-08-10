"""pipeline.run: upload named inputs -> inject -> queue -> await -> fetch -> verify -> save.

The default (prompt-only) path uploads *zero* images and does not regress. On top of that,
`run` now drives the **regenerate-until-detectable** loop: it renders, asks the injected
`FaceDetector` how many faces the result has, and re-seeds (`seed + 1`) and re-renders while
the count is not exactly one — bounded by `DEFAULT_MAX_ATTEMPTS`. On exhaustion it keeps the
last render and reports the failure (`detected=False`) instead of crashing. It also uploads
N named inputs by role, wiring each to its `LoadImage` node by title.
"""

from __future__ import annotations

from synthetic_portraits import pipeline
from synthetic_portraits.faces import FakeFaceDetector
from synthetic_portraits.models import get_model
from synthetic_portraits.pipeline import DEFAULT_MAX_ATTEMPTS
from synthetic_portraits.transport import FakeComfyClient
from synthetic_portraits.workflow import GenerationRequest, NamedInput

_ACCEPT = FakeFaceDetector([1])  # every render passes on the first attempt


def _seeds(fake: FakeComfyClient) -> list[int]:
    return [
        next(n for n in wf.values() if n["class_type"] == "KSampler")["inputs"]["seed"]
        for wf in fake.queued_workflows
    ]


# --- the default path does not regress -------------------------------------


def test_run_uploads_zero_inputs_for_prompt_only_and_saves_render(tmp_path):
    fake = FakeComfyClient(view_bytes=b"PNGDATA")
    model = get_model("realvis-txt2img")
    req = GenerationRequest(prompt="a photoreal upper-body portrait")

    outcome = pipeline.run(fake, model, req, out_dir=tmp_path, detector=FakeFaceDetector([1]))

    # Prompt-only path: nothing uploaded.
    assert fake.uploads == []
    # Exactly one workflow queued (accepted on the first attempt), carrying the prompt.
    assert len(fake.queued_workflows) == 1
    positive = next(
        n
        for n in fake.queued_workflows[0].values()
        if n["class_type"] == "CLIPTextEncode" and "Positive" in n["_meta"]["title"]
    )
    assert positive["inputs"]["text"] == "a photoreal upper-body portrait"
    # The default SaveImage output was fetched and written to disk.
    assert outcome.detected is True
    assert outcome.attempts == 1
    assert len(outcome.paths) == 1
    assert outcome.paths[0].read_bytes() == b"PNGDATA"
    assert outcome.paths[0].parent == tmp_path


def test_run_fetches_every_view_it_is_told_about(tmp_path):
    fake = FakeComfyClient()
    model = get_model("realvis-txt2img")

    pipeline.run(fake, model, GenerationRequest(prompt="p"), out_dir=tmp_path, detector=_ACCEPT)

    assert fake.requested_views == [("synthetic_portrait_00001_.png", "", "output")]


# --- the regenerate-until-detectable loop ----------------------------------


def test_accepts_first_render_when_one_face(tmp_path):
    fake = FakeComfyClient()
    model = get_model("realvis-txt2img")

    outcome = pipeline.run(
        fake,
        model,
        GenerationRequest(prompt="p", seed=5),
        out_dir=tmp_path,
        detector=FakeFaceDetector([1]),
    )

    assert outcome.detected is True
    assert outcome.attempts == 1
    assert outcome.faces == 1
    assert len(fake.queued_workflows) == 1  # no retries


def test_reseeds_and_retries_until_one_face(tmp_path):
    fake = FakeComfyClient()
    model = get_model("realvis-txt2img")
    # 0 faces, then 2 faces, then 1 face -> accept on the third attempt.
    det = FakeFaceDetector([0, 2, 1])

    outcome = pipeline.run(
        fake, model, GenerationRequest(prompt="p", seed=100), out_dir=tmp_path, detector=det
    )

    assert outcome.detected is True
    assert outcome.attempts == 3
    # Deterministic seed progression: seed, seed+1, seed+2.
    assert _seeds(fake) == [100, 101, 102]


def test_exhausts_attempts_keeps_last_render_and_reports_failure(tmp_path):
    fake = FakeComfyClient(view_bytes=b"LAST")
    model = get_model("realvis-txt2img")
    det = FakeFaceDetector([0])  # never one face

    outcome = pipeline.run(
        fake,
        model,
        GenerationRequest(prompt="p", seed=7),
        out_dir=tmp_path,
        detector=det,
        max_attempts=3,
    )

    assert outcome.detected is False
    assert outcome.attempts == 3
    assert len(fake.queued_workflows) == 3
    assert _seeds(fake) == [7, 8, 9]
    # Keeps the last render rather than crashing.
    assert len(outcome.paths) == 1
    assert outcome.paths[0].read_bytes() == b"LAST"


def test_max_attempts_defaults_to_the_module_constant(tmp_path):
    fake = FakeComfyClient()
    model = get_model("realvis-txt2img")
    det = FakeFaceDetector([0])  # always fails -> uses the full budget

    outcome = pipeline.run(
        fake, model, GenerationRequest(prompt="p"), out_dir=tmp_path, detector=det
    )

    assert DEFAULT_MAX_ATTEMPTS == 5
    assert outcome.attempts == DEFAULT_MAX_ATTEMPTS
    assert len(fake.queued_workflows) == DEFAULT_MAX_ATTEMPTS


# --- multi-input plumbing (role -> name upload map) -------------------------

_STUB_WITH_LOADIMAGE = {
    "1": {
        "class_type": "LoadImage",
        "_meta": {"title": "Load Image (identity)"},
        "inputs": {"image": "PLACEHOLDER"},
    },
    "6": {
        "class_type": "CLIPTextEncode",
        "_meta": {"title": "CLIP Text Encode (Positive)"},
        "inputs": {"text": "OLD", "clip": ["4", 1]},
    },
    "7": {
        "class_type": "CLIPTextEncode",
        "_meta": {"title": "CLIP Text Encode (Negative)"},
        "inputs": {"text": "OLD", "clip": ["4", 1]},
    },
    "5": {
        "class_type": "EmptyLatentImage",
        "_meta": {"title": "Empty Latent Image"},
        "inputs": {"width": 1, "height": 1, "batch_size": 1},
    },
    "3": {
        "class_type": "KSampler",
        "_meta": {"title": "KSampler"},
        "inputs": {
            "seed": 0,
            "positive": ["6", 0],
            "negative": ["7", 0],
            "latent_image": ["5", 0],
            "model": ["1", 0],
        },
    },
    "9": {
        "class_type": "SaveImage",
        "_meta": {"title": "Save Image"},
        "inputs": {"filename_prefix": "synthetic_portrait", "images": ["3", 0]},
    },
}


def test_uploads_named_input_and_wires_it_to_loadimage_by_role(tmp_path, monkeypatch):
    import json

    from synthetic_portraits import models

    # Point a throwaway model at the stub graph so we exercise the LoadImage wiring.
    wf_path = tmp_path / "stub.json"
    wf_path.write_text(json.dumps(_STUB_WITH_LOADIMAGE))
    model = models.Model(name="stub", workflow_path=wf_path, injector=models.inject_txt2img)

    fake = FakeComfyClient()
    req = GenerationRequest(
        prompt="same person",
        inputs=(NamedInput(role="identity", filename="hero.png", data=b"HERO"),),
    )

    pipeline.run(fake, model, req, out_dir=tmp_path, detector=_ACCEPT)

    # Uploaded exactly once, by role.
    assert fake.uploads == [("hero.png", b"HERO")]
    # Wired into the LoadImage node by its role/title, not a hardcoded id.
    load = next(n for n in fake.queued_workflows[0].values() if n["class_type"] == "LoadImage")
    assert load["inputs"]["image"] == "hero.png"


def test_named_input_uploaded_once_across_retries(tmp_path):
    import json

    from synthetic_portraits import models

    wf_path = tmp_path / "stub.json"
    wf_path.write_text(json.dumps(_STUB_WITH_LOADIMAGE))
    model = models.Model(name="stub", workflow_path=wf_path, injector=models.inject_txt2img)

    fake = FakeComfyClient()
    req = GenerationRequest(
        prompt="p",
        inputs=(NamedInput(role="identity", filename="hero.png", data=b"HERO"),),
    )
    det = FakeFaceDetector([0, 0, 1])  # two retries before acceptance

    pipeline.run(fake, model, req, out_dir=tmp_path, detector=det)

    # The hero is uploaded once, not re-uploaded per attempt.
    assert fake.uploads == [("hero.png", b"HERO")]
    assert len(fake.queued_workflows) == 3
