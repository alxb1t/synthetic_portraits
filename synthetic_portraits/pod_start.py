"""Start the pod: map the models onto the volume, provision them, serve ComfyUI.

The image's command, run by gpunit's boot script, which installs the session's key,
starts sshd, and stops the pod when this process ends. ComfyUI replaces this process.

Stdlib only and run as a file on the image's Python 3.10: the image holds this module
beside `provision.py`, not the package (0006 design D5).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
PROVISION = HERE / "provision.py"
MANIFEST = HERE / "models.json"
COMFYUI = Path("/opt/ComfyUI")

# The model folders ComfyUI reads from the volume through `extra_model_paths.yaml`.
FOLDERS = ("checkpoints", "controlnet", "instantid", "ultralytics", "insightface")

# The Impact Subpack and the InstantID node read these from ComfyUI's own `models/` and
# ignore the yaml; unlinked, the bbox list is empty and InstantID fetches a broken pack.
LINKED = ("ultralytics", "insightface")


def step(name: str) -> None:
    """Print the UTC time a step begins, so the log says where a boot's minutes go."""
    print(f"{datetime.now(timezone.utc):%Y-%m-%dT%H:%M:%SZ} step: {name}", flush=True)


def map_models(models: Path, comfyui: Path) -> None:
    """Point ComfyUI's model folders at `models`: the yaml for most, a link for the rest."""
    lines = ["volume:", f"  base_path: {models}", *(f"  {f}: {f}" for f in FOLDERS)]
    (comfyui / "extra_model_paths.yaml").write_text("\n".join(lines) + "\n")
    for folder in LINKED:
        (models / folder).mkdir(parents=True, exist_ok=True)
        link = comfyui / "models" / folder
        link.parent.mkdir(parents=True, exist_ok=True)
        if link.is_symlink():
            link.unlink()
        elif link.is_dir():
            # The image's own tree: no model is baked into the image.
            shutil.rmtree(link)
        link.symlink_to(models / folder)


def serve_comfyui(comfyui: Path) -> None:
    """Replace this process with ComfyUI, listening for the session's tunnel."""
    os.chdir(comfyui)
    os.execvp("python3", ["python3", "main.py", "--listen", "0.0.0.0", "--port", "8188"])


def main(
    env: Mapping[str, str] = os.environ,
    *,
    comfyui: Path = COMFYUI,
    run: Callable[..., subprocess.CompletedProcess[Any]] = subprocess.run,
    serve: Callable[[Path], None] = serve_comfyui,
) -> int:
    """Run every step in order; return 1 when one fails, and never return from a serve."""
    step("the volume")
    volume = env.get("GPUNIT_VOLUME_PATH", "")
    if not volume:
        print(
            "ERROR: GPUNIT_VOLUME_PATH is empty; refusing to provision onto the pod's own disk",
            file=sys.stderr,
        )
        return 1
    models = Path(volume) / "models"
    step("the model paths")
    map_models(models, comfyui)
    step("provisioning")
    command = [
        sys.executable,
        str(PROVISION),
        "fetch",
        "--models-dir",
        str(models),
        "--manifest",
        str(MANIFEST),
    ]
    fetched = run(command, check=False).returncode
    if fetched != 0:
        print(f"ERROR: provision.py fetch exited {fetched}; ComfyUI not started", file=sys.stderr)
        return 1
    step("ComfyUI")
    serve(comfyui)
    return 0


if __name__ == "__main__":
    sys.exit(main())
