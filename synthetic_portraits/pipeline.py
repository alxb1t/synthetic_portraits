"""The render pipeline: upload -> inject -> queue -> await -> fetch -> verify -> save.

``run`` drives the **regenerate-until-detectable** loop: it renders, asks the injected
:class:`~synthetic_portraits.faces.FaceDetector` how many faces the result has, and
re-seeds (``seed + 1``) and re-renders while the count is not exactly one — bounded by
``DEFAULT_MAX_ATTEMPTS``. On exhaustion it keeps the last render and reports the failure
(``detected=False``) rather than crashing, so one stubborn prompt never aborts a batch.

Named image inputs (e.g. the ``--identity`` hero) are uploaded **once** up front and wired
to their ``LoadImage`` nodes by role; the default prompt-only path uploads nothing.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING

from .transport import ComfyTransport, await_outputs
from .workflow import GenerationRequest, set_named_inputs

if TYPE_CHECKING:
    from .faces import FaceDetector
    from .models import Model

__all__ = ["DEFAULT_MAX_ATTEMPTS", "RenderOutcome", "RenderedImage", "render", "run"]

# Bounded retries for the regenerate-until-detectable loop. A named module constant (like
# DEFAULT_NEGATIVE), not a CLI flag — the pipeline owns the loop, so the default lives here.
DEFAULT_MAX_ATTEMPTS = 5


@dataclass(frozen=True)
class RenderedImage:
    filename: str
    data: bytes


@dataclass(frozen=True)
class RenderOutcome:
    """The result of one ``run``: the saved paths + whether the face check passed."""

    paths: list[Path]
    attempts: int
    detected: bool
    faces: int


def render(
    transport: ComfyTransport,
    model: Model,
    req: GenerationRequest,
    *,
    uploaded: dict[str, str] | None = None,
) -> list[RenderedImage]:
    """Inject the prompt, wire any already-uploaded inputs, queue, and fetch every image."""
    workflow = json.loads(Path(model.workflow_path).read_text())
    final = model.injector(workflow, req)
    if uploaded:
        set_named_inputs(final, uploaded)

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
    detector: FaceDetector,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
) -> RenderOutcome:
    """Render with the regenerate loop, then write the accepted (or last) render to disk.

    Uploads named inputs once, then renders up to ``max_attempts`` times advancing the seed
    each retry, accepting the first render with exactly one detectable face. On exhaustion it
    keeps and saves the last render and returns ``detected=False``.
    """
    uploaded = {ni.role: transport.upload_image(ni.filename, ni.data) for ni in req.inputs}

    images: list[RenderedImage] = []
    faces = 0
    detected = False
    attempts = 0
    for attempt in range(max(1, max_attempts)):
        attempts = attempt + 1
        attempt_req = replace(req, seed=req.seed + attempt)
        images = render(transport, model, attempt_req, uploaded=uploaded)
        detected, faces = _check(detector, images)
        if detected:
            break

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    saved: list[Path] = []
    for image in images:
        dest = out / image.filename
        dest.write_bytes(image.data)
        saved.append(dest)
    return RenderOutcome(paths=saved, attempts=attempts, detected=detected, faces=faces)


def _check(detector: FaceDetector, images: list[RenderedImage]) -> tuple[bool, int]:
    """A render is accepted iff it produced exactly one image with exactly one face."""
    if len(images) != 1:
        return False, 0
    faces = detector.count_faces(images[0].data)
    return faces == 1, faces
