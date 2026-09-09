"""Image-as-code guardrails (Phase 3).

Locks the conventions the plan calls out — the cu128 pin (Blackwell/sm_120), the model
download set, and shell-script syntax — as executable checks. No Docker build or network
here; ``docker build --check`` is deliberately outside the gate array (it needs a running
Docker daemon) — ``.github/workflows/build-image.yml`` builds the image for real on push.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCKERFILE = REPO_ROOT / "Dockerfile"
CONSTRAINTS = REPO_ROOT / "constraints.txt"
DOWNLOAD = REPO_ROOT / "download_models.sh"
START = REPO_ROOT / "infra" / "start.sh"
UP = REPO_ROOT / "infra" / "up.sh"
DOWN = REPO_ROOT / "infra" / "down.sh"

SHELL_SCRIPTS = [DOWNLOAD, START, UP, DOWN]


@pytest.mark.spec("pod.infra-files-present")
def test_infra_files_exist():
    for path in [DOCKERFILE, DOWNLOAD, START, UP, DOWN]:
        assert path.exists(), path


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash not available")
@pytest.mark.parametrize("script", SHELL_SCRIPTS, ids=lambda p: p.name)
@pytest.mark.spec("pod.scripts-syntax-clean")
def test_shell_scripts_pass_bash_syntax_check(script: Path):
    result = subprocess.run(["bash", "-n", str(script)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("script", SHELL_SCRIPTS, ids=lambda p: p.name)
@pytest.mark.spec("pod.scripts-strict-mode")
def test_shell_scripts_are_strict(script: Path):
    # Fail fast on errors/unset vars/pipe failures.
    assert "set -euo pipefail" in script.read_text()


@pytest.mark.spec("pod.pins-torch")
def test_dockerfile_pins_cu128_pytorch():
    # The Blackwell/sm_120 requirement — cu124 fails at runtime.
    assert "cu128" in DOCKERFILE.read_text()


@pytest.mark.spec("pod.pins-custom-nodes")
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


@pytest.mark.spec("pod.pins-face-deps")
def test_dockerfile_installs_face_and_detailer_deps_cpu_only():
    text = DOCKERFILE.read_text()
    # insightface + CPU onnxruntime + ultralytics power the face/detailer stack.
    assert "insightface" in text
    assert "onnxruntime" in text
    assert "ultralytics" in text
    # We never explicitly pip-install the GPU onnxruntime on our own line (Blackwell/cu128
    # CUDA-match pain). It may still arrive transitively via a node dep; that copy is
    # version-pinned through constraints.txt, not installed by us here.
    assert not re.search(r"pip3 install[^\n]*\bonnxruntime-gpu\b", text)


@pytest.mark.spec("pod.pins-face-deps")
def test_dockerfile_pins_face_and_detailer_deps_for_reproducible_builds():
    # Security S2: the four named deps are exact-pinned (== , not floating >=/unversioned),
    # and every requirements-file install is constraint-locked to the validated set so a
    # rebuild resolves the same tree instead of whatever PyPI serves that day.
    text = DOCKERFILE.read_text()
    assert "COPY constraints.txt" in text
    for pin in ("insightface==", "onnxruntime==", "ultralytics==", "numpy=="):
        assert pin in text, pin
    req_installs = [ln for ln in text.splitlines() if re.search(r"pip3 install .*-r ", ln)]
    assert req_installs, "expected requirements-file installs"
    for ln in req_installs:
        assert "-c /opt/constraints.txt" in ln, ln


@pytest.mark.spec("pod.constraints-fully-pinned")
def test_constraints_file_pins_every_line_exactly():
    # Every non-comment line is an exact `name==version` pin (no floating specifiers), and
    # no URL/VCS requirement (pip forbids those in a constraints file).
    lines = CONSTRAINTS.read_text().splitlines()
    pins = [ln.strip() for ln in lines if ln.strip() and not ln.lstrip().startswith("#")]
    assert pins, "expected version pins"
    for pin in pins:
        assert re.fullmatch(r"[A-Za-z0-9._-]+==[A-Za-z0-9._+!-]+", pin), pin
    assert not any(" @ " in pin for pin in pins), "no URL/VCS requirements in constraints"


def _constraint_pins() -> dict[str, str]:
    # `name==version` -> {name: version}, lowercased; comments and blanks dropped.
    pins: dict[str, str] = {}
    for raw in CONSTRAINTS.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        name, _, version = line.partition("==")
        pins[name.strip().lower()] = version.strip()
    return pins


def _major(version: str) -> int:
    return int(version.split(".")[0])


@pytest.mark.spec("pod.opencv-pins-agree")
def test_constraints_pin_one_opencv_version_across_both_distributions():
    """The two OpenCV builds must name the same upstream version.

    A regression guard, not a resolver: no test here may reach a package index, so this
    encodes the trap this repository actually hit rather than proving the set resolves.
    `build-image` remains the real proof (change 0004, design D2).

    Drift between these two pins is what produced the contradiction in `ca1669f`:
    `opencv-python` stayed at 4.11.0.86 while `opencv-python-headless` moved to 5.0.0.93,
    whose `numpy>=2` requirement cannot hold beside the pinned `numpy==1.26.4`.
    """
    pins = _constraint_pins()
    headless, regular = pins["opencv-python-headless"], pins["opencv-python"]
    assert headless == regular, (
        f"opencv-python-headless=={headless} disagrees with opencv-python=={regular}; "
        "the image would resolve two different OpenCV versions"
    )


@pytest.mark.spec("pod.constraints-mutually-satisfiable")
def test_constraints_numpy_pin_can_hold_beside_every_other_pin():
    """The pinned set must be satisfiable, not merely exactly pinned.

    `pod.constraints-fully-pinned` is satisfied by a set pip cannot resolve — which is
    exactly how the image build stayed red from 2026-08-10. OpenCV 5.x requires
    `numpy>=2`; the Impact Pack, which supplies FaceDetailer and
    UltralyticsDetectorProvider, caps numpy below 2. Both cannot hold (design D1/D2).
    """
    pins = _constraint_pins()
    numpy_pin = pins["numpy"]
    assert _major(numpy_pin) < 2, f"numpy=={numpy_pin} breaches the Impact Pack ceiling of <2"
    for dist in ("opencv-python", "opencv-python-headless"):
        assert _major(pins[dist]) < 5, (
            f"{dist}=={pins[dist]} requires numpy>=2, which cannot hold beside "
            f"the pinned numpy=={numpy_pin}"
        )


@pytest.mark.spec("pod.pins-face-deps")
def test_dockerfile_installs_requests():
    # ComfyUI imports `requests` (app/frontend_management.py) but does NOT declare it
    # in its requirements.txt — the minimal CUDA base lacks it, so ComfyUI crashes at
    # startup with ModuleNotFoundError unless we install it explicitly.
    assert "requests" in DOCKERFILE.read_text()


@pytest.mark.spec("pod.start-installs-ssh-key")
def test_start_installs_ssh_public_key():
    # FROM nvidia/cuda (not a RunPod base image) → start.sh must install RunPod's
    # injected PUBLIC_KEY into authorized_keys itself, or the SSH tunnel can't auth.
    text = START.read_text()
    assert "PUBLIC_KEY" in text
    assert "authorized_keys" in text


@pytest.mark.spec("pod.launches-via-start")
def test_dockerfile_launches_via_start_script():
    text = DOCKERFILE.read_text()
    assert "start.sh" in text
    assert 'CMD ["/opt/start.sh"]' in text


@pytest.mark.spec("pod.download-idempotent")
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


@pytest.mark.spec("pod.download-isolates")
def test_download_isolates_models_into_their_target_dirs():
    text = DOWNLOAD.read_text()
    # Subfolder-isolated targets (dodge generic-filename collisions like config.json).
    assert "instantid" in text  # models/instantid/ip-adapter.bin
    assert "controlnet" in text  # models/controlnet/...
    assert "insightface/models/antelopev2" in text  # the antelopev2 pack's ComfyUI path
    assert "ultralytics/bbox" in text  # face_yolov8m.pt


@pytest.mark.spec("pod.download-pins-revisions")
def test_download_pins_immutable_commit_revisions():
    # Supply chain (security S1): every HF `resolve/<ref>/` must pin an IMMUTABLE commit SHA,
    # never the mutable `main` branch — so a moved ref (or a compromised mirror force-moving
    # `main`) can't silently swap the bytes we fetch. The URLs interpolate a `*_REV` variable;
    # assert no `main` ref, that each resolve ref is a `_REV` var (or a literal SHA), and that
    # every `_REV` variable is assigned a real 40-hex commit SHA.
    text = DOWNLOAD.read_text()
    assert "resolve/main/" not in text, "model URLs must not use the mutable `main` ref"
    refs = re.findall(r"/resolve/([^/]+)/", text)
    assert refs, "expected pinned resolve URLs"
    for ref in refs:
        assert re.fullmatch(r"[0-9a-f]{40}", ref) or re.fullmatch(r"\$\{\w*REV\w*\}", ref), (
            f"resolve ref is neither a 40-hex commit SHA nor a *_REV pin: {ref}"
        )
    rev_defs = re.findall(r"^\w*REV\w*=\"?([^\"\n]+)\"?", text, re.MULTILINE)
    assert rev_defs, "expected *_REV pin definitions"
    for rev in rev_defs:
        assert re.fullmatch(r"[0-9a-f]{40}", rev), f"*_REV pin is not a 40-hex commit SHA: {rev}"


@pytest.mark.spec("pod.download-verifies-sha256")
def test_download_verifies_sha256_and_aborts_on_mismatch():
    # Security S1: two weights are code-executing pickle (.bin/.pt) loaded via torch.load-style
    # paths, from third-party mirrors. Every download must be SHA-256 verified, and a mismatch
    # must ABORT (non-zero exit) so a swapped/corrupt file is never moved into place.
    text = DOWNLOAD.read_text()
    assert "sha256sum" in text
    assert "exit 1" in text  # checksum mismatch aborts the script
    # The pickle weights specifically carry their recorded SHA-256 (the highest-risk files).
    assert "02b3618e36d803784166660520098089a81388e61a93ef8002aa79a5b1c546e1" in text  # ip-adapter
    assert "717923c19b3f4bbf5250b728f1fa6b2cb72a33aed1d236ea9caf0e21ad943e5f" in text  # yolov8m


@pytest.mark.spec("pod.download-verifies-sha256")
def test_download_records_a_checksum_for_every_fetched_file():
    # Every download call passes a SHA-256 argument (a `_SHA` var, a literal, or the antelope
    # `ANTELOPE_SHAS[i]` array) — no unverified fetch slips through. And every `_SHA` pin is a
    # real 64-hex digest.
    text = DOWNLOAD.read_text()
    download_calls = [ln for ln in text.splitlines() if re.match(r"\s*download ", ln)]
    assert download_calls, "expected download calls"
    for ln in download_calls:
        assert re.search(r"[0-9a-f]{64}", ln) or "_SHA" in ln or "SHAS" in ln, ln
    sha_defs = re.findall(r"^\w*_SHA=\"?([^\"\n]+)\"?", text, re.MULTILINE)
    assert sha_defs, "expected *_SHA pin definitions"
    for sha in sha_defs:
        assert re.fullmatch(r"[0-9a-f]{64}", sha), f"*_SHA pin is not a 64-hex digest: {sha}"


@pytest.mark.spec("pod.start-maps-model-dirs")
def test_start_maps_the_v0_2_model_dirs_into_comfyui():
    # ComfyUI code is in the image, weights on the volume — extra_model_paths must expose
    # the new model folders (controlnet/instantid/ultralytics/insightface), not just checkpoints.
    text = START.read_text()
    for folder in ("controlnet", "instantid", "ultralytics", "insightface"):
        assert folder in text, folder


@pytest.mark.spec("pod.start-maps-model-dirs")
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


@pytest.mark.spec("pod.uses-rest-api")
def test_pod_scripts_use_runpod_rest_api():
    # Both talk to the documented REST base; auth is a bearer token from the env/.env,
    # never a hardcoded secret.
    for script in (UP, DOWN):
        text = script.read_text()
        assert "rest.runpod.io/v1" in text, script
        assert "RUNPOD_API_KEY" in text, script
        assert "Bearer" in text, script


@pytest.mark.spec("pod.up-persists-id")
def test_up_creates_a_gpu_pod_and_persists_its_id():
    text = UP.read_text()
    # Creates a pod (POST /pods) on a GPU with the models network volume attached, and
    # records the pod id so down.sh can tear exactly it down.
    assert "POST" in text
    assert "/pods" in text
    assert "gpuTypeIds" in text
    assert "networkVolumeId" in text
    assert ".pod_id" in text  # id persisted for teardown


@pytest.mark.spec("pod.up-enables-ssh")
def test_up_enables_ssh_tunnel_access():
    text = UP.read_text()
    # These SECURE + network-volume pods have no usable HTTP path (RunPod's Cloudflare
    # proxy 403s API POSTs), so we drive ComfyUI over an SSH tunnel: inject the SSH
    # public key, expose 22/tcp, and forward local 8188 to the pod.
    assert "PUBLIC_KEY" in text
    assert "22/tcp" in text
    assert "-L" in text  # ssh local port-forward
    assert ":localhost:" in text  # forwards the ComfyUI port through the tunnel


@pytest.mark.spec("pod.down-deletes")
def test_down_deletes_the_pod():
    text = DOWN.read_text()
    # Teardown is a DELETE against the recorded pod id — stops per-second billing.
    assert "DELETE" in text
    assert "/pods/" in text
    assert ".pod_id" in text


@pytest.mark.spec("pod.id-file-untracked")
def test_pod_id_state_file_is_gitignored():
    # The pod-id scratch file is per-run local state, never committed.
    gitignore = (REPO_ROOT / ".gitignore").read_text()
    assert ".pod_id" in gitignore
