"""The render pipeline: inject -> queue -> await -> fetch -> save.

Pose is prompt-driven, so no path uploads an input image; the pipeline injects the prompt
into the graph, renders, and writes the results.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from .transport import ComfyTransport, await_outputs
from .workflow import GenerationRequest

if TYPE_CHECKING:
    from .models import Model

__all__ = ["RenderedImage", "render", "run"]


@dataclass(frozen=True)
class RenderedImage:
    filename: str
    data: bytes


def render(
    transport: ComfyTransport,
    model: Model,
    req: GenerationRequest,
) -> list[RenderedImage]:
    """Inject the prompt, queue the graph, and fetch every rendered image."""
    workflow = json.loads(Path(model.workflow_path).read_text())
    final = model.injector(workflow, req)

    prompt_id = transport.queue_prompt(final)
    outputs = await_outputs(transport, prompt_id)

    images: list[RenderedImage] = []
    for node_output in outputs.values():
        for image in node_output.get("images", []):
            data = transport.get_image(
                image["filename"], image.get("subfolder", ""), image.get("type", "output")
            )
            images.append(RenderedImage(image["filename"], data))
    return images


def run(
    transport: ComfyTransport,
    model: Model,
    req: GenerationRequest,
    *,
    out_dir: str | Path,
) -> list[Path]:
    """Render, then write each image into ``out_dir``; return the written paths."""
    images = render(transport, model, req)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []
    for image in images:
        dest = out / image.filename
        dest.write_bytes(image.data)
        saved.append(dest)
    return saved
