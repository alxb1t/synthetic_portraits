"""The OpenPose-ControlNet path: inject_pose + multi-input dispatch + --pose-image.

The pose graph routes KSampler.positive *through* ControlNetApplyAdvanced (which references
both encoders), so the conditioning trace must be branch-aware — the prompt lands on the
positive encoder, never the negative one. The prompt-only path must stay un-regressed.
"""

from __future__ import annotations

import copy

import pytest

from synthetic_portraits import cli, pipeline
from synthetic_portraits.models import get_model
from synthetic_portraits.transport import FakeComfyClient
from synthetic_portraits.workflow import GenerationRequest, WorkflowError, inject_pose


def _node_by_title(wf: dict, class_type: str, needle: str) -> dict:
    for node in wf.values():
        if node["class_type"] == class_type and needle in node["_meta"]["title"]:
            return node
    raise AssertionError(f"no {class_type} titled ~{needle!r}")


# --- inject_pose ------------------------------------------------------------


def test_inject_pose_sets_prompt_on_positive_encoder_through_controlnet(pose_workflow):
    req = GenerationRequest(prompt="a man in a leather jacket", inputs={"pose": "up.png"})

    result = inject_pose(pose_workflow, req)

    positive = _node_by_title(result, "CLIPTextEncode", "Positive")
    negative = _node_by_title(result, "CLIPTextEncode", "Negative")
    assert positive["inputs"]["text"] == "a man in a leather jacket"
    # The branch-aware trace must NOT have written the prompt onto the negative encoder.
    assert negative["inputs"]["text"] != "a man in a leather jacket"


def test_inject_pose_sets_negative_on_negative_encoder(pose_workflow):
    req = GenerationRequest(prompt="p", negative="bad hands", inputs={"pose": "up.png"})

    result = inject_pose(pose_workflow, req)

    assert _node_by_title(result, "CLIPTextEncode", "Negative")["inputs"]["text"] == "bad hands"


def test_inject_pose_wires_uploaded_pose_into_the_load_image(pose_workflow):
    req = GenerationRequest(prompt="p", inputs={"pose": "uploaded_pose_123.png"})

    result = inject_pose(pose_workflow, req)

    load = _node_by_title(result, "LoadImage", "Pose")
    assert load["inputs"]["image"] == "uploaded_pose_123.png"


def test_inject_pose_still_sets_dims_and_seed(pose_workflow):
    req = GenerationRequest(prompt="p", width=768, height=1152, seed=99, inputs={"pose": "u.png"})

    result = inject_pose(pose_workflow, req)

    latent = next(n for n in result.values() if n["class_type"] == "EmptyLatentImage")
    ksampler = next(n for n in result.values() if n["class_type"] == "KSampler")
    assert (latent["inputs"]["width"], latent["inputs"]["height"]) == (768, 1152)
    assert ksampler["inputs"]["seed"] == 99


def test_inject_pose_does_not_mutate_input(pose_workflow):
    original = copy.deepcopy(pose_workflow)
    inject_pose(pose_workflow, GenerationRequest(prompt="x", inputs={"pose": "u.png"}))
    assert pose_workflow == original


def test_inject_pose_raises_when_no_pose_input_provided(pose_workflow):
    with pytest.raises(WorkflowError, match="pose"):
        inject_pose(pose_workflow, GenerationRequest(prompt="p"))  # empty inputs map


# --- dispatch + pipeline ----------------------------------------------------


def test_pose_model_is_registered_with_pose_input_and_injector():
    model = get_model("realvis-txt2img-pose")
    assert model.injector is inject_pose
    assert model.inputs == ("pose",)
    assert model.workflow_path.name == "realvis-txt2img-pose.json"


def test_pipeline_uploads_the_pose_reference_and_wires_it(tmp_path):
    pose = tmp_path / "pose.png"
    pose.write_bytes(b"POSEBYTES")
    fake = FakeComfyClient()
    model = get_model("realvis-txt2img-pose")

    pipeline.run(
        fake, model, GenerationRequest(prompt="p"),
        out_dir=tmp_path, input_files={"pose": str(pose)},
    )

    # The pose file was uploaded exactly once...
    assert fake.uploads == [("pose.png", b"POSEBYTES")]
    # ...and its uploaded name was wired into the pose LoadImage of the queued graph.
    load = _node_by_title(fake.queued_workflows[0], "LoadImage", "Pose")
    assert load["inputs"]["image"] == "pose.png"


# --- CLI --------------------------------------------------------------------


def test_cli_pose_image_routes_through_the_pose_model(tmp_path):
    pose = tmp_path / "ref.png"
    pose.write_bytes(b"REF")
    fake = FakeComfyClient()

    rc = cli.main(
        ["--model", "realvis-txt2img-pose", "--prompt", "a dancer",
         "--pose-image", str(pose), "--out", str(tmp_path)],
        transport=fake,
    )

    assert rc == 0
    assert fake.uploads == [("ref.png", b"REF")]


def test_cli_pose_model_requires_a_pose_image(tmp_path):
    argv = ["--model", "realvis-txt2img-pose", "--prompt", "p", "--out", str(tmp_path)]
    with pytest.raises(SystemExit) as exc:
        cli.main(argv, transport=FakeComfyClient())
    assert exc.value.code != 0


def test_cli_pose_image_rejected_for_prompt_only_model(tmp_path):
    pose = tmp_path / "ref.png"
    pose.write_bytes(b"REF")
    argv = ["--prompt", "p", "--pose-image", str(pose), "--out", str(tmp_path)]
    with pytest.raises(SystemExit) as exc:
        cli.main(argv, transport=FakeComfyClient())
    assert exc.value.code != 0


def test_prompt_only_path_unregressed_uploads_nothing(tmp_path):
    fake = FakeComfyClient()
    cli.main(["--prompt", "p", "--out", str(tmp_path)], transport=fake)
    assert fake.uploads == []
