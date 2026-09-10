"""Image-as-code guardrails (Phase 3).

Locks the conventions the plan calls out — the cu128 pin (Blackwell/sm_120), the model
download set, and shell-script syntax — as executable checks. No Docker build or network
here; ``docker build --check`` is deliberately outside the gate array (it needs a running
Docker daemon) — ``.github/workflows/build-image.yml`` builds the image for real on push.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCKERFILE = REPO_ROOT / "Dockerfile"
CONSTRAINTS = REPO_ROOT / "constraints.txt"
DOWNLOAD = REPO_ROOT / "download_models.sh"
START = REPO_ROOT / "infra" / "start.sh"
UP = REPO_ROOT / "infra" / "up.sh"
DOWN = REPO_ROOT / "infra" / "down.sh"
BUILD_IMAGE = REPO_ROOT / ".github" / "workflows" / "build-image.yml"
CHECK_FACE = REPO_ROOT / "scripts" / "check_face.py"

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


@pytest.mark.spec("pod.constraints-fully-pinned")
def test_constraints_file_pins_every_line_exactly():
    # Every non-comment line is an exact `name==version` pin (no floating specifiers), and
    # no URL/VCS requirement (pip forbids those in a constraints file).
    pins = [f"{name}=={version}" for name, version in _constraint_pins().items()]
    assert pins, "expected version pins"
    for pin in pins:
        assert re.fullmatch(r"[A-Za-z0-9._-]+==[A-Za-z0-9._+!-]+", pin), pin
    assert not any(" @ " in pin for pin in pins), "no URL/VCS requirements in constraints"


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


# --- Bounded readiness, self-teardown, opt-in HTTP (change 0004, D3/D6) ------


def _up_payload_ports(**env: str) -> list[str]:
    """Run up.sh's payload builder with a controlled environment; return its ports list.

    The heredoc is executed rather than pattern-matched, so this asserts what the script
    actually sends to the provider rather than what its source appears to say.
    """
    match = re.search(r"python3 <<'PY'\n(.*?)\nPY\n", UP.read_text(), re.S)
    assert match, "up.sh no longer contains the payload-builder heredoc"
    snippet = match.group(1)
    base = {
        "RUNPOD_NAME": "test-pod",
        "RUNPOD_IMG": "example/image:latest",
        "RUNPOD_GPU": "TEST GPU",
        "RUNPOD_DISK": "30",
        "RUNPOD_MNT": "/runpod-volume",
        "RUNPOD_VOL": "volumeid",
        "RUNPOD_DC": "",
        "RUNPOD_PUBKEY": "ssh-ed25519 AAAA test",
    }
    proc = subprocess.run(
        [sys.executable, "-c", snippet],
        env={**base, **env},
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(proc.stdout)["ports"]


def _curl_invocations(path: Path) -> list[str]:
    """Return each `curl` command in a shell script as one line, continuations joined.

    A backslash-continued invocation is several source lines but one command, and its
    flags may sit on any of them — so the flags are asserted against the joined command
    rather than against the line the word ``curl`` happens to appear on.
    """
    joined = re.sub(r"\\\n\s*", " ", path.read_text())
    return [
        ln.strip()
        for ln in joined.splitlines()
        if re.search(r"(^|[\s$(`])curl\s", ln) and not ln.strip().startswith("#")
    ]


@pytest.mark.spec("pod.up-bounded-readiness")
def test_every_provider_call_is_bounded_against_a_hung_connection():
    # The readiness deadline is only tested BETWEEN iterations, so it can fire only if every
    # curl inside the loop returns. curl has no default transfer timeout: a half-open TCP
    # connection through a NAT, or a provider-side stall, blocks in the loop forever, SECONDS
    # sails past the deadline, down.sh is never reached, and the pod bills for the length of
    # the stall — the unbounded billing D6 exists to convert into a three-minute loss. The
    # EXIT trap cannot help: it runs when the script exits, and the script is not exiting.
    #
    # down.sh is held to the same bar for the sharper version of the same failure: a teardown
    # that hangs leaves the operator believing the pod was deleted while it is still billing.
    for script in (UP, DOWN):
        invocations = _curl_invocations(script)
        assert invocations, f"{script.name} makes no curl call"
        for call in invocations:
            assert re.search(r"(--max-time|\s-m)\s", call), (
                f"{script.name} calls curl with no transfer timeout, so it can hang "
                f"past every deadline: {call}"
            )


@pytest.mark.spec("pod.up-tears-down-on-timeout")
def test_up_says_a_pod_may_exist_when_the_id_cannot_be_read():
    # The EXIT trap is installed after the create response is parsed, so one window is not
    # covered by it: the provider creates the pod but the client never sees a usable id —
    # curl interrupted after creation, an unexpected response shape, a parse failure. The
    # script exits 1 and the operator concludes nothing was created, while .pod_id is absent
    # so down.sh has nothing to delete and the pod bills until someone opens the console.
    # The trap cannot cover it (there is no id to tear down), so the failure must be SAID.
    text = UP.read_text()
    branch = text.split('if [ -z "$pod_id" ]; then', 1)
    assert len(branch) == 2, "up.sh no longer guards against an unreadable pod id"
    branch = branch[1].split("\nfi\n", 1)[0]

    assert "may have been created" in branch, (
        "the unreadable-id path must warn that a pod may be live and billing"
    )
    assert "POD_NAME" in branch, "the warning must name the pod so the console can be checked"


@pytest.mark.spec("pod.up-http-port-opt-in")
def test_up_requests_only_the_tunnelled_port_by_default():
    # The provider serves an HTTP-exposed port at a PUBLIC, UNAUTHENTICATED URL, and
    # ComfyUI has no auth of its own. Publishing it must be a decision, not a default —
    # the shipped `pod.up-enables-ssh` scenario says "without exposing a public port".
    assert _up_payload_ports() == ["22/tcp"]


@pytest.mark.spec("pod.up-http-port-opt-in")
def test_up_publishes_the_http_port_only_when_explicitly_opted_in():
    ports = _up_payload_ports(RUNPOD_EXPOSE_HTTP="1")

    assert "22/tcp" in ports, "opting into HTTP must not cost the tunnel"
    assert any("8188" in p for p in ports)


@pytest.mark.spec("pod.up-bounded-readiness")
def test_up_bounds_readiness_with_a_longer_deadline_for_the_fallback():
    # A pod that reaches RUNNING without becoming reachable bills indefinitely for nothing.
    # The fallback gets longer because ComfyUI must also finish starting behind the proxy.
    text = UP.read_text()
    tunnel_match = re.search(r"READY_DEADLINE_TUNNEL_SECS:-(\d+)", text)
    proxy_match = re.search(r"READY_DEADLINE_PROXY_SECS:-(\d+)", text)
    assert tunnel_match, "up.sh declares no tunnelled readiness deadline"
    assert proxy_match, "up.sh declares no fallback readiness deadline"

    tunnel, proxy = int(tunnel_match.group(1)), int(proxy_match.group(1))

    assert tunnel > 0 and proxy > 0
    assert proxy > tunnel, f"fallback deadline {proxy}s must exceed tunnelled {tunnel}s"


@pytest.mark.spec("pod.up-tears-down-on-timeout")
def test_up_tears_the_pod_down_when_readiness_expires():
    # Teardown reuses down.sh so there is ONE code path that stops billing. A hand-rolled
    # DELETE here would be a second one to keep correct.
    text = UP.read_text()

    # Must be an INVOCATION, not a mention. up.sh already prints "tear down with:
    # infra/down.sh" as advice, and advice does not stop billing.
    #
    # The invocation lives in an EXIT trap rather than only in the timeout branch: the
    # deadline is one way to exit with a live pod, but a failed curl under `set -e`, a
    # parse error or a Ctrl-C are others, and all of them bill. One trap covers the class.
    trap_line = next(
        (ln for ln in text.splitlines() if ln.startswith("trap ") and "EXIT" in ln), ""
    )
    assert trap_line, "up.sh installs no EXIT trap, so an abnormal exit leaves a pod billing"
    assert "down.sh" in trap_line, "the EXIT trap must execute down.sh"
    assert 'rc" -eq 0' in trap_line, "the trap must not tear down a pod on a successful exit"
    assert "trap - EXIT" in text, "the success path must hand the pod over, not tear it down"
    assert "DELETE" not in text, "up.sh must not hand-roll its own delete"


@pytest.mark.spec("pod.up-polls-the-path-in-use")
def test_up_accepts_proxy_readiness_when_the_http_port_is_published():
    # Measured 2026-09-09/10: EU-RO-1 is capacity-starved, so pods reach RUNNING with no
    # publicIp and no portMappings — the tunnel can never be reached. The proxy route needs
    # no public IP and works exactly then, so waiting LONGER for an address that will never
    # arrive tears down a pod that was reachable all along. Readiness must test the route in
    # use, not a different one.
    # Asserted against the probe's own CODE line, not the file. An earlier version of this
    # test checked `"system_stats" in text` and sliced the file between two string anchors;
    # both were satisfied by the pre-fix script — the slice caught an unrelated EXPOSE_HTTP
    # check in the success branch, and the surviving assertion matched the explanatory
    # COMMENT above the probe. Deleting the whole fix but keeping its comment left it green.
    code = [ln for ln in UP.read_text().splitlines() if not ln.strip().startswith("#")]

    probes = [ln for ln in code if "system_stats" in ln]
    assert probes, "up.sh does not probe the render server on the published HTTP route"
    probe = probes[0]

    assert "PROXY_URL" in probe, "the probe must target the published proxy route"
    assert "EXPOSE_HTTP" in probe, "the proxy probe must be conditional on opting in"
    assert any("proxy_ready" in ln and "=" in ln for ln in code), (
        "a pod reachable only over the proxy must be recorded as ready, not torn down"
    )


# --- build-image publishes what the pod pulls (change 0004, D9) --------------


@pytest.mark.spec("pod.image-prune-is-default-branch-only")
def test_the_registry_prune_never_runs_off_the_default_branch():
    # Measured 2026-09-10. `latest` is tagged only on the default branch, but the prune
    # step ran on EVERY push — so running build-image against a feature branch pushed a
    # sha- tag and then deleted every older version, INCLUDING the only `latest` that
    # existed. `up.sh` defaults to :latest, so three pods failed with
    # IMAGE_NOT_FOUND/manifest unknown against a registry holding one sha- tag.
    #
    # A green workflow run is not the check: that run WAS green. The destructive step has
    # to be gated on the branch that also produces the tag it is allowed to supersede.
    text = BUILD_IMAGE.read_text()
    prune = [ln for ln in text.splitlines() if "delete-package-versions" in ln]
    assert prune, "build-image no longer prunes; delete this guard with the step"

    block = text.split("delete-package-versions", 1)[1]
    guarded = "default_branch" in text.split("delete-package-versions")[0].rsplit("- name:", 1)[-1]
    assert guarded, (
        "the prune step must be gated on the default branch — off it, the run deletes "
        "the `latest` it cannot republish"
    )
    assert "min-versions-to-keep" in block


@pytest.mark.spec("pod.image-branch-runs-keep-latest")
def test_the_image_the_pod_pulls_by_default_is_the_one_the_workflow_tags():
    # up.sh's default image reference and the workflow's raw tag are one string. If the
    # workflow stops emitting `latest`, every pod created without RUNPOD_IMAGE fails to
    # pull — which is exactly what happened, and nothing in the suite noticed.
    workflow = BUILD_IMAGE.read_text()
    up = UP.read_text()

    assert "value=latest" in workflow, "build-image no longer publishes a `latest` tag"
    assert ":latest}" in up or ':latest"' in up or ":latest" in up, (
        "up.sh no longer defaults to :latest — retire this pairing deliberately"
    )


# --- the readiness loop sees a dead container (change 0004, D10) -------------


def _up_readiness_fields(pod_json: str) -> list[str]:
    """Run up.sh's readiness parser over one provider response; return its fields.

    Executed rather than pattern-matched, like ``_up_payload_ports`` — this asserts what
    the loop actually reads out of the response, not what its source appears to say.
    """
    match = re.search(r"python3 -c '\n(import sys, json\n.*?)\n'", UP.read_text(), re.S)
    assert match, "up.sh no longer contains the inline readiness parser"
    proc = subprocess.run(
        [sys.executable, "-c", match.group(1)],
        input=pod_json,
        env={"PATH": os.environ["PATH"]},
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout.split()


@pytest.mark.spec("pod.up-fails-fast-on-a-dead-container")
def test_the_readiness_parser_reports_the_container_status():
    # Measured 2026-09-10: three pods whose image could not be pulled sat at EXITED within
    # seconds, and up.sh waited out its FULL deadline on each — it reads only publicIp and
    # portMappings, so a container that died at second 5 looks exactly like one still
    # starting. The status is in the same response the loop already parses.
    fields = _up_readiness_fields('{"publicIp": null, "portMappings": null, "status": "EXITED"}')

    assert "EXITED" in fields, "the readiness parser discards the container status"


@pytest.mark.spec("pod.up-fails-fast-on-a-dead-container")
def test_a_missing_status_field_is_not_treated_as_a_dead_container():
    # Fail-open on purpose. `status` is confirmed on GET /pods/{id}; this loop calls the
    # ?id= QUERY form, and that it carries the field is not proven here — a grep or a
    # parse test cannot prove what the provider returns. So an absent status must read as
    # "keep waiting", exactly as today, and only an explicit terminal state aborts. That
    # way shipping this cannot regress a pod that would otherwise have come up.
    fields = _up_readiness_fields('{"publicIp": null, "portMappings": null}')

    assert "EXITED" not in fields and "TERMINATED" not in fields


@pytest.mark.spec("pod.up-fails-fast-on-a-dead-container")
def test_up_aborts_on_a_terminal_container_status():
    # Aborting means exit under `set -e`, which is an exit, which is the EXIT trap — so
    # the dead pod is torn down rather than left billing out the rest of the deadline.
    code = [ln for ln in UP.read_text().splitlines() if not ln.strip().startswith("#")]
    text = "\n".join(code)

    assert "EXITED" in text and "TERMINATED" in text, (
        "up.sh does not recognise a terminal container status"
    )
    assert "DELETE" not in text, "up.sh must still not hand-roll its own delete"


# --- check_face.py runs as documented (change 0004, D10) ---------------------


@pytest.mark.spec("faces.check-face-runs-as-documented")
def test_check_face_can_import_the_package_when_run_as_a_script():
    # `python scripts/check_face.py` puts scripts/ on sys.path, NOT the repo root, and
    # `[tool.uv] package = false` means the package is never installed into the venv —
    # so the `from synthetic_portraits.faces import ensure_antelopev2` that 422fa03 added
    # for security S3 cannot resolve. The documented invocation has been broken since
    # 2026-08-10; the unit tests never caught it because they inject a fake detector and
    # never reach that import.
    #
    # sys.path[0] = scripts/ and a foreign cwd together reproduce exactly what Python does
    # for a script under scripts/, with no chance of the working directory rescuing it.
    code = (
        "import sys; sys.path.insert(0, sys.argv[1]); "
        "import check_face; import synthetic_portraits; print('ok')"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code, str(CHECK_FACE.parent)],
        cwd=tempfile.gettempdir(),
        env={"PATH": os.environ["PATH"]},
        capture_output=True,
        text=True,
    )

    assert proc.returncode == 0, (
        f"check_face.py cannot import the package when run as a script: {proc.stderr}"
    )
    assert "ok" in proc.stdout
