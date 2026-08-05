"""The render pipeline: upload named inputs -> inject -> queue -> await -> fetch -> save.

The prompt-only path passes an empty input map and uploads nothing. Phase 4 adds the pose
reference as a named input via the same uniform ``role -> uploaded_name`` map, so this
path is unaffected.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING

from .transport import ComfyTransport, await_outputs
from .workflow import GenerationRequest

if TYPE_CHECKING:
    from collections.abc import Mapping

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
    *,
    input_files: Mapping[str, str] | None = None,
) -> list[RenderedImage]:
    """Upload inputs, inject, queue the graph, and fetch every rendered image."""
    uploaded: dict[str, str] = {}
    for role, path in dict(input_files or {}).items():
        local = Path(path)
        uploaded[role] = transport.upload_image(local.name, local.read_bytes())

    workflow = json.loads(Path(model.workflow_path).read_text())
    final = model.injector(workflow, replace(req, inputs=uploaded))

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
    input_files: Mapping[str, str] | None = None,
) -> list[Path]:
    """Render, then write each image into ``out_dir``; return the written paths."""
    images = render(transport, model, req, input_files=input_files)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []
    for image in images:
        dest = out / image.filename
        dest.write_bytes(image.data)
        saved.append(dest)
    return saved
