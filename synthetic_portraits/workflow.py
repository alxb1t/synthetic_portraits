"""Workflow injection — set the prompt/dims/seed by *tracing* the graph, not by id.

A workflow JSON is a graph of numbered nodes; each ``inputs`` value is either a literal
or a link ``[node_id, output_index]``. To place the prompt we find the ``KSampler`` and
follow its ``positive``/``negative`` links to the first ``CLIPTextEncode``, and its
``latent_image`` link to the ``EmptyLatentImage``. That single traversal keeps working
when node ids change between the placeholder fixture and the real GPU export.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "DEFAULT_HEIGHT",
    "DEFAULT_NEGATIVE",
    "DEFAULT_WIDTH",
    "GenerationRequest",
    "WorkflowError",
    "inject_txt2img",
]

# Default portrait aspect for upper-body framing (the EmptyLatentImage dims).
DEFAULT_WIDTH = 832
DEFAULT_HEIGHT = 1216

# A baseline negative prompt; tuned for hands/anatomy in Phase 5 (upper-body can show hands).
DEFAULT_NEGATIVE = (
    "deformed, disfigured, bad anatomy, extra fingers, mutated hands, "
    "blurry, low quality, watermark, text, cartoon, 3d render"
)

Workflow = dict[str, Any]


class WorkflowError(Exception):
    """The workflow graph is missing a node the injector needs."""


@dataclass(frozen=True)
class GenerationRequest:
    """Everything the injector + pipeline need to render one image.

    ``inputs`` maps a role (e.g. ``"pose"``) to an uploaded server-side name; the
    prompt-only path leaves it empty. Populated by the pipeline after upload (Phase 4).
    """

    prompt: str
    negative: str = DEFAULT_NEGATIVE
    width: int = DEFAULT_WIDTH
    height: int = DEFAULT_HEIGHT
    seed: int = 0
    inputs: Mapping[str, str] = field(default_factory=dict)


def inject_txt2img(workflow: Workflow, req: GenerationRequest) -> Workflow:
    """Return a copy of ``workflow`` with the prompt/dims/seed wired in.

    Does not mutate the input graph.
    """
    wf = copy.deepcopy(workflow)
    ksampler = _find_by_class(wf, "KSampler")

    positive_id = _resolve_upstream(wf, ksampler["inputs"]["positive"], "CLIPTextEncode")
    wf[positive_id]["inputs"]["text"] = req.prompt

    negative_id = _resolve_upstream(wf, ksampler["inputs"]["negative"], "CLIPTextEncode")
    wf[negative_id]["inputs"]["text"] = req.negative

    latent_id = _resolve_upstream(wf, ksampler["inputs"]["latent_image"], "EmptyLatentImage")
    wf[latent_id]["inputs"]["width"] = req.width
    wf[latent_id]["inputs"]["height"] = req.height

    ksampler["inputs"]["seed"] = req.seed
    return wf


# --- graph tracing helpers --------------------------------------------------


def _find_by_class(workflow: Workflow, class_type: str) -> dict[str, Any]:
    for node in workflow.values():
        if node.get("class_type") == class_type:
            return node
    raise WorkflowError(f"no {class_type} node in workflow")


def _is_link(value: Any) -> bool:
    return (
        isinstance(value, (list, tuple))
        and len(value) == 2
        and isinstance(value[0], str)
        and isinstance(value[1], int)
    )


def _resolve_upstream(workflow: Workflow, link: Any, class_type: str) -> str:
    """Walk upstream from ``link`` to the first node of ``class_type``; return its id."""
    seen: set[str] = set()
    stack: list[Any] = [link]
    while stack:
        current = stack.pop()
        if not _is_link(current):
            continue
        node_id = current[0]
        if node_id in seen:
            continue
        seen.add(node_id)
        node = workflow.get(node_id)
        if node is None:
            continue
        if node.get("class_type") == class_type:
            return node_id
        stack.extend(node.get("inputs", {}).values())
    raise WorkflowError(f"could not trace a {class_type} upstream of {link!r}")
