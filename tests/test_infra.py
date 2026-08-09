"""Image-as-code guardrails (Phase 3).

Locks the conventions the plan calls out — the cu128 pin (Blackwell/sm_120), the model
download set, and shell-script syntax — as executable checks. No Docker build or network
here; ``docker build --check`` runs in the gate.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCKERFILE = REPO_ROOT / "Dockerfile"
DOWNLOAD = REPO_ROOT / "download_models.sh"
START = REPO_ROOT / "infra" / "start.sh"
UP = REPO_ROOT / "infra" / "up.sh"
DOWN = REPO_ROOT / "infra" / "down.sh"

SHELL_SCRIPTS = [DOWNLOAD, START, UP, DOWN]


def test_infra_files_exist():
    for path in [DOCKERFILE, DOWNLOAD, START, UP, DOWN]:
        assert path.exists(), path


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash not available")
@pytest.mark.parametrize("script", SHELL_SCRIPTS, ids=lambda p: p.name)
def test_shell_scripts_pass_bash_syntax_check(script: Path):
    result = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("script", SHELL_SCRIPTS, ids=lambda p: p.name)
def test_shell_scripts_are_strict(script: Path):
    # Fail fast on errors/unset vars/pipe failures.
    assert "set -euo pipefail" in script.read_text()


def test_dockerfile_pins_cu128_pytorch():
    # The Blackwell/sm_120 requirement — cu124 fails at runtime.
    assert "cu128" in DOCKERFILE.read_text()


def test_dockerfile_pins_v0_2_custom_nodes():
    # InstantID + FaceDetailer (Impact Pack + Subpack) nodes, pinned to the exact commits
    # verified in v0.2_research (Phase 0). Pins, not floating HEAD — reproducible builds.
    text = DOCKERFILE.read_text()
    assert "ComfyUI_InstantID" in text
    assert "72495e806bc2ab9c41581e15ccaa1bcf83c477e8" in text
    assert "ComfyUI-Impact-Pack" in text
    assert "429d0159ad429e64d2b3916e6e7be9c22d025c3c" in text
    assert "ComfyUI-Impact-Subpack" in text
    assert "50c7b71a6a224734cc9b21963c6d1926816a97f1" in text


def test_dockerfile_installs_face_and_detailer_deps_cpu_only():
    text = DOCKERFILE.read_text()
    # insightface + CPU onnxruntime + ultralytics; the Impact Pack numpy<2 ceiling pinned.
    assert "insightface" in text
    assert "onnxruntime" in text
    assert "ultralytics" in text
    assert "numpy<2" in text
    # Never the GPU onnxruntime (Blackwell/cu128 CUDA-match pain; never install both).
    assert "onnxruntime-gpu" not in text


def test_dockerfile_installs_requests():
    # ComfyUI imports `requests` (app/frontend_management.py) but does NOT declare it
    # in its requirements.txt — the minimal CUDA base lacks it, so ComfyUI crashes at
    # startup with ModuleNotFoundError unless we install it explicitly.
    assert "requests" in DOCKERFILE.read_text()


def test_start_installs_ssh_public_key():
    # FROM nvidia/cuda (not a RunPod base image) → start.sh must install RunPod's
    # injected PUBLIC_KEY into authorized_keys itself, or the SSH tunnel can't auth.
    text = START.read_text()
    assert "PUBLIC_KEY" in text
    assert "authorized_keys" in text


def test_dockerfile_launches_via_start_script():
    text = DOCKERFILE.read_text()
    assert "start.sh" in text
    assert 'CMD ["/opt/start.sh"]' in text


def test_download_is_idempotent_and_fetches_the_v0_2_model_set():
    text = DOWNLOAD.read_text()
    # Exact HF filename — the repo ships fp16/fp32 variants; the bare
    # RealVisXL_V5.0.safetensors does NOT exist (a boot-time 404 crash-loop bug).
    assert "RealVisXL_V5.0_fp16.safetensors" in text
    assert "skip" in text.lower()  # skips files already present (idempotent)
    url_lines = [ln for ln in text.splitlines() if "https://" in ln]
    # v0.2 adds the InstantID stack + the FaceDetailer bbox model, from the pinned sources.
    assert any("InstantX/InstantID" in ln and "ip-adapter.bin" in ln for ln in url_lines)
    assert any("ControlNetModel" in ln for ln in url_lines)  # identity ControlNet
    assert any("antelopev2" in ln for ln in url_lines)  # the 5-file insightface pack
    assert any("face_yolov8m.pt" in ln for ln in url_lines)  # FaceDetailer bbox detector


def test_download_isolates_models_into_their_target_dirs():
    text = DOWNLOAD.read_text()
    # Subfolder-isolated targets (dodge generic-filename collisions like config.json).
    assert "instantid" in text  # models/instantid/ip-adapter.bin
    assert "controlnet" in text  # models/controlnet/...
    assert "insightface/models/antelopev2" in text  # the antelopev2 pack's ComfyUI path
    assert "ultralytics/bbox" in text  # face_yolov8m.pt


def test_start_maps_the_v0_2_model_dirs_into_comfyui():
    # ComfyUI code is in the image, weights on the volume — extra_model_paths must expose
    # the new model folders (controlnet/instantid/ultralytics/insightface), not just checkpoints.
    text = START.read_text()
    for folder in ("controlnet", "instantid", "ultralytics", "insightface"):
        assert folder in text, folder


def test_start_symlinks_hardcoded_model_dirs_to_the_volume():
    # The Impact Subpack (UltralyticsDetectorProvider) and the InstantID node resolve models
    # from ``folder_paths.models_dir/<x>`` directly and IGNORE extra_model_paths.yaml — so the
    # yaml mapping alone leaves the bbox list empty and makes InstantID auto-download a broken
    # (nested) antelopev2. start.sh must symlink those two dirs onto the volume before ComfyUI
    # launches. (Discovered live in Phase 6.)
    text = START.read_text()
    for folder in ("ultralytics", "insightface"):
        # a symlink of ComfyUI's models/<folder> -> the volume's <folder>
        assert re.search(rf"ln -s\S*\s+\S*{folder}\S*\s+\S*models/{folder}", text), folder


def test_pod_scripts_use_runpod_rest_api():
    # Both talk to the documented REST base; auth is a bearer token from the env/.env,
    # never a hardcoded secret.
    for script in (UP, DOWN):
        text = script.read_text()
        assert "rest.runpod.io/v1" in text, script
        assert "RUNPOD_API_KEY" in text, script
        assert "Bearer" in text, script


def test_up_creates_a_gpu_pod_and_persists_its_id():
    text = UP.read_text()
    # Creates a pod (POST /pods) on a GPU with the models network volume attached, and
    # records the pod id so down.sh can tear exactly it down.
    assert "POST" in text
    assert "/pods" in text
    assert "gpuTypeIds" in text
    assert "networkVolumeId" in text
    assert ".pod_id" in text  # id persisted for teardown


def test_up_enables_ssh_tunnel_access():
    text = UP.read_text()
    # These SECURE + network-volume pods have no usable HTTP path (RunPod's Cloudflare
    # proxy 403s API POSTs), so we drive ComfyUI over an SSH tunnel: inject the SSH
    # public key, expose 22/tcp, and forward local 8188 to the pod.
    assert "PUBLIC_KEY" in text
    assert "22/tcp" in text
    assert "-L" in text  # ssh local port-forward
    assert ":localhost:" in text  # forwards the ComfyUI port through the tunnel


def test_down_deletes_the_pod():
    text = DOWN.read_text()
    # Teardown is a DELETE against the recorded pod id — stops per-second billing.
    assert "DELETE" in text
    assert "/pods/" in text
    assert ".pod_id" in text


def test_pod_id_state_file_is_gitignored():
    # The pod-id scratch file is per-run local state, never committed.
    gitignore = (REPO_ROOT / ".gitignore").read_text()
    assert ".pod_id" in gitignore
