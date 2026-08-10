"""The name -> Model registry (Registry + Strategy).

A model name maps to a frozen :class:`Model` that owns its workflow graph and its injector.
Dispatch is a dict lookup — no ``if/elif`` chains. Two internal graphs share the one
generalized injector: the hardened default (``realvis-txt2img``) and the same graph plus the
InstantID legs (``realvis-txt2img-identity``). The CLI selects the identity graph
automatically when ``--identity`` supplies a hero — the graphs are an implementation detail,
not a menu the user picks from.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .workflow import GenerationRequest, Workflow, inject_txt2img

__all__ = [
    "DEFAULT_MODEL",
    "IDENTITY_MODEL",
    "MODELS",
    "SELECTABLE_MODELS",
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


MODELS: dict[str, Model] = {
    "realvis-txt2img": Model(
        name="realvis-txt2img",
        workflow_path=WORKFLOWS_DIR / "realvis-txt2img.json",
        injector=inject_txt2img,
    ),
    "realvis-txt2img-identity": Model(
        name="realvis-txt2img-identity",
        workflow_path=WORKFLOWS_DIR / "realvis-txt2img-identity.json",
        injector=inject_txt2img,  # the one generalized injector serves both graphs
    ),
}

DEFAULT_MODEL = "realvis-txt2img"
IDENTITY_MODEL = "realvis-txt2img-identity"

# The user-selectable ``--model`` menu. The identity graph is deliberately excluded: it is an
# internal implementation detail auto-selected by ``--identity`` (which uploads the hero), never
# chosen by name. Selecting it without a hero would queue a graph whose ``LoadImage`` still holds
# a placeholder — a footgun that only surfaces at (paid) GPU time. It stays in ``MODELS`` for
# internal dispatch but is kept off the menu.
SELECTABLE_MODELS: tuple[str, ...] = tuple(
    sorted(name for name in MODELS if name != IDENTITY_MODEL)
)


def get_model(name: str) -> Model:
    try:
        return MODELS[name]
    except KeyError:
        available = ", ".join(sorted(MODELS))
        raise UnknownModelError(f"unknown model {name!r}; available: {available}") from None
