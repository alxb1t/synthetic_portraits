"""The --identity path: one generalized injector serves the InstantID graph too.

The identity graph inserts an ``ApplyInstantID`` node between the ``KSampler`` and the
``CLIPTextEncode`` encoders, carrying **both** positive and negative conditioning. So the
prompt trace is now **two hops** (``KSampler.positive`` -> ``ApplyInstantID`` -> the first
``CLIPTextEncode``) and must follow the input by **role** — positive to the positive
encoder, negative to the negative encoder — not blindly grab the first encoder it meets.
The same ``inject_txt2img`` handles both the one-hop default and the two-hop identity graph.
"""

from __future__ import annotations

from synthetic_portraits.models import IDENTITY_MODEL, get_model
from synthetic_portraits.workflow import GenerationRequest, inject_txt2img


def _encoder_text(wf: dict, want_title: str) -> str:
    node = next(
        n
        for n in wf.values()
        if n["class_type"] == "CLIPTextEncode" and want_title in n["_meta"]["title"]
    )
    return node["inputs"]["text"]


# --- the identity model is registered and uses the shared injector ----------


def test_identity_model_registered_with_the_shared_injector():
    model = get_model(IDENTITY_MODEL)
    assert model.injector is inject_txt2img
    assert model.workflow_path.name == "realvis-txt2img-identity.json"


def test_identity_fixture_has_the_instantid_legs(identity_workflow):
    classes = {n["class_type"] for n in identity_workflow.values()}
    assert "InstantIDModelLoader" in classes
    assert "InstantIDFaceAnalysis" in classes
    assert "ApplyInstantID" in classes
    assert "ControlNetLoader" in classes  # the identity ControlNet
    # A hero LoadImage wired by the "identity" role/title.
    load = next(n for n in identity_workflow.values() if n["class_type"] == "LoadImage")
    assert "identity" in load["_meta"]["title"].lower()
    # It still carries the hardening (hi-res + FaceDetailer).
    assert "FaceDetailer" in classes
    assert len([n for n in identity_workflow.values() if n["class_type"] == "KSampler"]) == 2


def test_apply_instantid_sits_between_ksampler_and_the_encoders(identity_workflow):
    ksampler = next(
        n
        for n in identity_workflow.values()
        if n["class_type"] == "KSampler" and "Base" in n["_meta"]["title"]
    )
    pos_feeder = identity_workflow[ksampler["inputs"]["positive"][0]]
    assert pos_feeder["class_type"] == "ApplyInstantID"


# --- the two-hop trace lands on the right encoder by role -------------------


def test_two_hop_trace_sets_positive_on_the_positive_encoder(identity_workflow):
    result = inject_txt2img(identity_workflow, GenerationRequest(prompt="same person, cafe"))

    assert _encoder_text(result, "Positive") == "same person, cafe"


def test_two_hop_trace_does_not_leak_prompt_into_the_negative_encoder(identity_workflow):
    req = GenerationRequest(prompt="POSITIVE ONLY", negative="NEGATIVE ONLY")

    result = inject_txt2img(identity_workflow, req)

    # Role-aware: positive prompt on the positive encoder, negative on the negative one.
    assert _encoder_text(result, "Positive") == "POSITIVE ONLY"
    assert _encoder_text(result, "Negative") == "NEGATIVE ONLY"


def test_two_hop_trace_still_sets_dims_and_seed(identity_workflow):
    result = inject_txt2img(
        identity_workflow, GenerationRequest(prompt="p", width=768, height=1152, seed=99)
    )

    latent = next(n for n in result.values() if n["class_type"] == "EmptyLatentImage")
    assert (latent["inputs"]["width"], latent["inputs"]["height"]) == (768, 1152)
    seeds = [n["inputs"]["seed"] for n in result.values() if n["class_type"] == "KSampler"]
    assert seeds == [99, 99]
