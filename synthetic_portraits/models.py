"""The name -> Model registry (Registry + Strategy).

``--model`` maps to a frozen :class:`Model` that owns its workflow graph and its injector.
Dispatch is a dict lookup — no ``if/elif`` chains. Phase 4 adds ``realvis-txt2img-pose``.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from .workflow import GenerationRequest, Workflow, inject_txt2img

__all__ = [
    "DEFAULT_MODEL",
    "MODELS",
    "Model",
    "UnknownModelError",
    "get_model",
]

WORKFLOWS_DIR = Path(__file__).resolve().parent.parent / "workflows"

Injector = Callable[[Workflow, GenerationRequest], Workflow]


class UnknownModelError(KeyError):
    """The requested ``--model`` name is not registered."""


@dataclass(frozen=True)
class Model:
    """A registered generation strategy: a workflow graph + how to inject into it."""

    name: str
    workflow_path: Path
    injector: Injector
    # Named image inputs (roles) this model requires; prompt-only txt2img needs none.
    inputs: tuple[str, ...] = field(default=())


MODELS: dict[str, Model] = {
    "realvis-txt2img": Model(
        name="realvis-txt2img",
        workflow_path=WORKFLOWS_DIR / "realvis-txt2img.json",
        injector=inject_txt2img,
        inputs=(),
    ),
}

DEFAULT_MODEL = "realvis-txt2img"


def get_model(name: str) -> Model:
    try:
        return MODELS[name]
    except KeyError:
        available = ", ".join(sorted(MODELS))
        raise UnknownModelError(f"unknown model {name!r}; available: {available}") from None
