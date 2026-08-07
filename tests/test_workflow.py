"""inject_txt2img: wire the prompt/dims/seed into the graph by *tracing*, not by id.

The injector never hardcodes a node id — it finds the ``KSampler`` and follows its
``positive``/``negative``/``latent_image`` links to the right nodes, so it keeps working
when ids change between the placeholder fixture and the real GPU export.
"""

from __future__ import annotations

import copy

import pytest

from synthetic_portraits.workflow import (
    GenerationRequest,
    WorkflowError,
    inject_txt2img,
)


def _positive_id(wf: dict) -> str:
    for nid, node in wf.items():
        if node["class_type"] == "CLIPTextEncode" and "Positive" in node["_meta"]["title"]:
            return nid
    raise AssertionError("no positive encoder in fixture")


def test_inject_sets_prompt_on_the_positive_encoder(txt2img_workflow):
    req = GenerationRequest(prompt="a calm woman, studio portrait")

    result = inject_txt2img(txt2img_workflow, req)

    pos = _positive_id(txt2img_workflow)
    assert result[pos]["inputs"]["text"] == "a calm woman, studio portrait"


def test_inject_sets_negative_prompt_on_the_negative_encoder(txt2img_workflow):
    req = GenerationRequest(prompt="p", negative="extra fingers, blurry")

    result = inject_txt2img(txt2img_workflow, req)

    # The negative encoder is the one the KSampler's `negative` input resolves to.
    neg_link = next(n for n in result.values() if n["class_type"] == "KSampler")["inputs"][
        "negative"
    ]
    assert result[neg_link[0]]["inputs"]["text"] == "extra fingers, blurry"


def test_inject_sets_dimensions_on_empty_latent_image(txt2img_workflow):
    req = GenerationRequest(prompt="p", width=768, height=1152)

    result = inject_txt2img(txt2img_workflow, req)

    latent = next(n for n in result.values() if n["class_type"] == "EmptyLatentImage")
    assert latent["inputs"]["width"] == 768
    assert latent["inputs"]["height"] == 1152


def test_inject_sets_seed_on_ksampler(txt2img_workflow):
    req = GenerationRequest(prompt="p", seed=12345)

    result = inject_txt2img(txt2img_workflow, req)

    ksampler = next(n for n in result.values() if n["class_type"] == "KSampler")
    assert ksampler["inputs"]["seed"] == 12345


def test_inject_does_not_mutate_the_input_workflow(txt2img_workflow):
    original = copy.deepcopy(txt2img_workflow)

    inject_txt2img(txt2img_workflow, GenerationRequest(prompt="changed"))

    assert txt2img_workflow == original


def test_inject_traces_by_role_not_by_hardcoded_id():
    # Same roles, deliberately unusual ids/order — tracing must still find them.
    wf = {
        "sampler": {
            "class_type": "KSampler",
            "_meta": {"title": "KSampler"},
            "inputs": {
                "seed": 0,
                "positive": ["pos", 0],
                "negative": ["neg", 0],
                "latent_image": ["lat", 0],
                "model": ["ckpt", 0],
            },
        },
        "pos": {
            "class_type": "CLIPTextEncode",
            "_meta": {"title": "CLIP Text Encode (Positive)"},
            "inputs": {"text": "OLD", "clip": ["ckpt", 1]},
        },
        "neg": {
            "class_type": "CLIPTextEncode",
            "_meta": {"title": "CLIP Text Encode (Negative)"},
            "inputs": {"text": "OLD", "clip": ["ckpt", 1]},
        },
        "lat": {
            "class_type": "EmptyLatentImage",
            "_meta": {"title": "Empty Latent Image"},
            "inputs": {"width": 1, "height": 1, "batch_size": 1},
        },
        "ckpt": {"class_type": "CheckpointLoaderSimple", "_meta": {}, "inputs": {}},
    }

    result = inject_txt2img(wf, GenerationRequest(prompt="NEW", width=832, height=1216))

    assert result["pos"]["inputs"]["text"] == "NEW"
    assert result["lat"]["inputs"]["width"] == 832


def test_inject_raises_when_ksampler_is_missing():
    graph = {"x": {"class_type": "VAEDecode", "inputs": {}}}
    with pytest.raises(WorkflowError, match="KSampler"):
        inject_txt2img(graph, GenerationRequest(prompt="p"))
