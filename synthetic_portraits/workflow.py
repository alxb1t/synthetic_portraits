"""Workflow injection — set the prompt/dims/seed by *tracing* the graph, not by id.

A workflow JSON is a graph of numbered nodes; each ``inputs`` value is either a literal
or a link ``[node_id, output_index]``. To place the prompt we find the ``KSampler`` and
follow its ``positive``/``negative`` links to the first ``CLIPTextEncode``, and its
``latent_image`` link to the ``EmptyLatentImage``. That single traversal keeps working
when node ids change between the placeholder fixture and the real GPU export.

Pose is prompt-driven (no reference image, no ControlNet) — described in the prompt text.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass
from typing import Any

__all__ = [
    "DEFAULT_HEIGHT",
    "DEFAULT_NEGATIVE",
    "DEFAULT_WIDTH",
    "GenerationRequest",
    "NamedInput",
    "WorkflowError",
    "inject_txt2img",
    "set_named_inputs",
]

# Default portrait aspect for upper-body framing (the EmptyLatentImage dims).
DEFAULT_WIDTH = 832
DEFAULT_HEIGHT = 1216

# Hands/anatomy negative, validated on RealVisXL V5.0 in Phase 5 (upper-body can show hands).
DEFAULT_NEGATIVE = (
    "deformed, distorted, disfigured, bad anatomy, extra limbs, missing limbs, "
    "poorly drawn face, "
    "blurry, low quality, worst quality, jpeg artifacts, cartoon, anime, 3d, cgi, render, "
    "painting, illustration, plastic skin, airbrushed, watermark, text, signature"
)

Workflow = dict[str, Any]


class WorkflowError(Exception):
    """The workflow graph is missing a node the injector needs."""


@dataclass(frozen=True)
class NamedInput:
    """One image the pipeline uploads and wires to a ``LoadImage`` node **by role**.

    ``role`` matches the target ``LoadImage`` node's title (e.g. ``"identity"`` for the hero
    image); ``filename`` is the name to upload as; ``data`` is the raw image bytes.
    """

    role: str
    filename: str
    data: bytes


@dataclass(frozen=True)
class GenerationRequest:
    """Everything the injector + pipeline need to render one image."""

    prompt: str
    negative: str = DEFAULT_NEGATIVE
    width: int = DEFAULT_WIDTH
    height: int = DEFAULT_HEIGHT
    seed: int = 0
    # Named image inputs to upload + wire by role (empty on the default prompt-only path).
    inputs: tuple[NamedInput, ...] = ()


def inject_txt2img(workflow: Workflow, req: GenerationRequest) -> Workflow:
    """Return a copy of ``workflow`` with the prompt/dims/seed wired in.

    Traces from a ``KSampler`` to the right nodes (never by id), so it survives the
    node-id churn between the placeholder fixture and the real GPU export. The hardened
    graph has **two** ``KSampler`` passes (base + latent hi-res); prompt/dims are traced
    from the first (both passes share the same encoders + latent chain) and the **seed is
    set on every pass** so re-seeding in the regenerate loop re-rolls the person and stays
    reproducible. Does not mutate the input graph.
    """
    wf = copy.deepcopy(workflow)
    ksamplers = _find_all_by_class(wf, "KSampler")
    first = ksamplers[0]

    positive_id = _resolve_upstream(wf, first["inputs"]["positive"], "CLIPTextEncode")
    wf[positive_id]["inputs"]["text"] = req.prompt

    negative_id = _resolve_upstream(wf, first["inputs"]["negative"], "CLIPTextEncode")
    wf[negative_id]["inputs"]["text"] = req.negative

    latent_id = _resolve_upstream(wf, first["inputs"]["latent_image"], "EmptyLatentImage")
    wf[latent_id]["inputs"]["width"] = req.width
    wf[latent_id]["inputs"]["height"] = req.height

    for ksampler in ksamplers:
        ksampler["inputs"]["seed"] = req.seed
    return wf


def set_named_inputs(workflow: Workflow, uploaded: dict[str, str]) -> Workflow:
    """Wire each ``role -> server_name`` onto its ``LoadImage`` node **in place**, by title.

    Generalizes v0.1's zero-input assumption: the pipeline uploads N named inputs and points
    each ``LoadImage`` at the uploaded name — matched by the node's role/title (like
    injection-by-trace), never by a hardcoded id. Raises :class:`WorkflowError` if a declared
    role has no matching ``LoadImage`` node. An empty map is a no-op (the default path).
    """
    for role, server_name in uploaded.items():
        node = _find_load_image_by_role(workflow, role)
        node["inputs"]["image"] = server_name
    return workflow


# --- graph tracing helpers --------------------------------------------------


def _find_load_image_by_role(workflow: Workflow, role: str) -> dict[str, Any]:
    needle = role.casefold()
    for node in workflow.values():
        if node.get("class_type") != "LoadImage":
            continue
        title = node.get("_meta", {}).get("title", "")
        if needle in title.casefold():
            return node
    raise WorkflowError(f"no LoadImage node for role {role!r}")


def _find_all_by_class(workflow: Workflow, class_type: str) -> list[dict[str, Any]]:
    nodes = [n for n in workflow.values() if n.get("class_type") == class_type]
    if not nodes:
        raise WorkflowError(f"no {class_type} node in workflow")
    return nodes


def _is_link(value: Any) -> bool:
    """A node input is a link when it is ``[node_id: str, output_index: int]``."""
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
