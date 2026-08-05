"""Registry + Strategy: --model name -> a frozen Model(workflow_path, injector)."""

from __future__ import annotations

import pytest

from synthetic_portraits.models import (
    DEFAULT_MODEL,
    MODELS,
    UnknownModelError,
    get_model,
)
from synthetic_portraits.workflow import inject_txt2img


def test_realvis_txt2img_is_registered_with_its_injector():
    model = get_model("realvis-txt2img")
    assert model.injector is inject_txt2img
    assert model.workflow_path.name == "realvis-txt2img.json"
    assert model.inputs == ()  # prompt-only: no named image inputs


def test_registered_workflow_files_exist():
    for model in MODELS.values():
        assert model.workflow_path.exists(), model.workflow_path


def test_default_model_is_the_prompt_only_txt2img():
    assert DEFAULT_MODEL == "realvis-txt2img"


def test_unknown_model_raises_with_available_names():
    with pytest.raises(UnknownModelError, match="realvis-txt2img"):
        get_model("does-not-exist")
