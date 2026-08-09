"""inject_txt2img: wire the prompt/dims/seed into the graph by *tracing*, not by id.

The injector never hardcodes a node id — it finds the ``KSampler`` and follows its
``positive``/``negative``/``latent_image`` links to the right nodes, so it keeps working
when ids change between the placeholder fixture and the real GPU export.
"""

from __future__ import annotations

import copy

import pytest

from synthetic_portraits.workflow import (
    DEFAULT_NEGATIVE,
    GenerationRequest,
    WorkflowError,
    inject_txt2img,
    set_named_inputs,
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


# --- multi-input wiring: role -> LoadImage by title, not by id --------------


def _graph_with_load_image() -> dict:
    return {
        "1": {
            "class_type": "LoadImage",
            "_meta": {"title": "Load Image (identity)"},
            "inputs": {"image": "PLACEHOLDER"},
        },
        "2": {
            "class_type": "SaveImage",
            "_meta": {"title": "Save Image"},
            "inputs": {"images": ["1", 0]},
        },
    }


def test_set_named_inputs_wires_server_name_onto_loadimage_by_role():
    wf = _graph_with_load_image()

    set_named_inputs(wf, {"identity": "hero_srv.png"})

    assert wf["1"]["inputs"]["image"] == "hero_srv.png"


def test_set_named_inputs_matches_role_case_insensitively():
    wf = _graph_with_load_image()

    set_named_inputs(wf, {"IDENTITY": "hero_srv.png"})

    assert wf["1"]["inputs"]["image"] == "hero_srv.png"


def test_set_named_inputs_empty_map_is_a_noop():
    wf = _graph_with_load_image()
    before = copy.deepcopy(wf)

    set_named_inputs(wf, {})

    assert wf == before


def test_set_named_inputs_raises_when_no_loadimage_matches_the_role():
    wf = _graph_with_load_image()
    with pytest.raises(WorkflowError, match="pose"):
        set_named_inputs(wf, {"pose": "x.png"})


# --- the hardened default graph: base -> hi-res -> FaceDetailer -------------


def _ksamplers(wf: dict) -> list[dict]:
    return [n for n in wf.values() if n["class_type"] == "KSampler"]


def test_hardened_fixture_has_hires_and_facedetailer_topology(txt2img_workflow):
    classes = {n["class_type"] for n in txt2img_workflow.values()}
    # base txt2img -> latent hi-res (upscale + 2nd sampler) -> FaceDetailer -> save.
    assert "LatentUpscaleBy" in classes
    assert "FaceDetailer" in classes
    assert "UltralyticsDetectorProvider" in classes  # the bbox detector for FaceDetailer
    assert len(_ksamplers(txt2img_workflow)) == 2  # base + hi-res second pass


def test_hires_second_ksampler_resamples_the_upscaled_latent(txt2img_workflow):
    # The hi-res KSampler's latent must come (via LatentUpscaleBy) from the base KSampler.
    upscale = next(
        n for n in txt2img_workflow.values() if n["class_type"] == "LatentUpscaleBy"
    )
    src_id = upscale["inputs"]["samples"][0]
    assert txt2img_workflow[src_id]["class_type"] == "KSampler"  # fed by the base sampler


def test_facedetailer_is_the_final_image_before_save(txt2img_workflow):
    save = next(n for n in txt2img_workflow.values() if n["class_type"] == "SaveImage")
    feeder_id = save["inputs"]["images"][0]
    assert txt2img_workflow[feeder_id]["class_type"] == "FaceDetailer"


def test_inject_sets_seed_on_every_ksampler(txt2img_workflow):
    # Both passes get the seed, so re-seeding in the regenerate loop actually re-rolls the
    # person (base sampler) and stays reproducible (hi-res sampler).
    result = inject_txt2img(txt2img_workflow, GenerationRequest(prompt="p", seed=4242))

    seeds = [k["inputs"]["seed"] for k in _ksamplers(result)]
    assert seeds == [4242, 4242]


def test_inject_traces_dims_through_the_hires_hop(txt2img_workflow):
    # EmptyLatentImage still gets the dims even though the hi-res sampler sits a
    # LatentUpscaleBy hop away from it — tracing walks upstream, not by id.
    result = inject_txt2img(txt2img_workflow, GenerationRequest(prompt="p", width=768, height=1152))

    latent = next(n for n in result.values() if n["class_type"] == "EmptyLatentImage")
    assert (latent["inputs"]["width"], latent["inputs"]["height"]) == (768, 1152)


# --- the loosened negative (v0.1 post-ship tweak, carried) ------------------


def test_default_negative_allows_visible_hands():
    # Upper-body / full-height shots legitimately show hands; the negative must not
    # suppress them (carried from v0.1's post-ship tweak).
    lowered = DEFAULT_NEGATIVE.lower()
    assert "hand" not in lowered
    assert "finger" not in lowered


def test_default_negative_keeps_the_face_guard():
    assert "poorly drawn face" in DEFAULT_NEGATIVE.lower()
