"""pipeline.run: upload named inputs -> inject -> queue -> await -> fetch -> save.

The prompt-only txt2img path uploads *zero* images; the injected graph carries the
prompt; rendered bytes are written to the output dir.
"""

from __future__ import annotations

from synthetic_portraits import pipeline
from synthetic_portraits.models import get_model
from synthetic_portraits.transport import FakeComfyClient
from synthetic_portraits.workflow import GenerationRequest


def test_run_uploads_zero_inputs_for_prompt_only_and_saves_render(tmp_path):
    fake = FakeComfyClient(view_bytes=b"PNGDATA")
    model = get_model("realvis-txt2img")
    req = GenerationRequest(prompt="a photoreal upper-body portrait")

    saved = pipeline.run(fake, model, req, out_dir=tmp_path)

    # Prompt-only path: nothing uploaded.
    assert fake.uploads == []
    # Exactly one workflow queued, carrying the prompt after injection.
    assert len(fake.queued_workflows) == 1
    queued = fake.queued_workflows[0]
    positive = next(
        n for n in queued.values()
        if n["class_type"] == "CLIPTextEncode" and "Positive" in n["_meta"]["title"]
    )
    assert positive["inputs"]["text"] == "a photoreal upper-body portrait"
    # The default SaveImage output was fetched and written to disk.
    assert len(saved) == 1
    assert saved[0].read_bytes() == b"PNGDATA"
    assert saved[0].parent == tmp_path


def test_run_fetches_every_view_it_is_told_about(tmp_path):
    fake = FakeComfyClient()
    model = get_model("realvis-txt2img")

    pipeline.run(fake, model, GenerationRequest(prompt="p"), out_dir=tmp_path)

    # The fake's default outputs advertise one image; the pipeline must fetch it via /view.
    assert fake.requested_views == [("synthetic_portrait_00001_.png", "", "output")]
