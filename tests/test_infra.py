"""Image-as-code guardrails: the build file, its constraints, the session's spec, the workflow.

No Docker build or network here; ``docker build --check`` is deliberately outside the gate
(it needs a running Docker daemon) — ``.github/workflows/build-image.yml`` builds the image
for real.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import tomllib
from collections.abc import Mapping
from pathlib import Path

import pytest
from gpunit.spec import parse_ceiling

REPO_ROOT = Path(__file__).resolve().parent.parent
DOCKERFILE = REPO_ROOT / "Dockerfile"
GPUNIT_SPEC = REPO_ROOT / "gpunit.toml"
IMAGE_CONFIG = REPO_ROOT / "config" / "image.json"
CONSTRAINTS = REPO_ROOT / "constraints.txt"
BUILD_IMAGE = REPO_ROOT / ".github" / "workflows" / "build-image.yml"
CHECK_FACE = REPO_ROOT / "scripts" / "check_face.py"


def shell_scripts(paths: list[str]) -> list[str]:
    """Return each path that names a shell script."""
    return [path for path in paths if path.endswith((".sh", ".bash"))]


@pytest.mark.spec_exempt("structural: the pod boots in Python, and no shell script is left")
def test_no_shell_script_is_left_in_the_repository():
    tracked = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    assert shell_scripts(tracked) == []


@pytest.mark.spec_exempt("structural: twin of test_no_shell_script_is_left_in_the_repository")
def test_the_shell_script_check_catches_a_script():
    assert shell_scripts(["Dockerfile", "infra/up.sh", "boot.bash", "notes.md"]) == [
        "infra/up.sh",
        "boot.bash",
    ]


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


# --- gpunit.toml is the session's spec: the pin, the floors, the ceiling, the volume -------


def spec_faults(spec: Mapping[str, object], config: Mapping[str, object]) -> list[str]:
    """Return each way `gpunit.toml` misses the pin, the floors, the ceiling or the volume.

    e.g. `image = "ghcr.io/a/b:latest"`, no `volume` -> ["not config/image.json's pin", "no volume"]
    """
    faults = []
    digest = str(config.get("digest", ""))
    pinned = f"{config.get('image')}@{digest}"
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest) or spec.get("image") != pinned:
        faults.append("not config/image.json's pin")
    try:
        ceiling_s = parse_ceiling(str(spec.get("ceiling", "")))
    except ValueError:
        ceiling_s = None
    if ceiling_s is None or ceiling_s > 45 * 60:
        faults.append("no ceiling within 45 minutes")
    if not spec.get("volume"):
        faults.append("no volume")
    vram = spec.get("vram_gb")
    if not (isinstance(vram, int) and vram >= 24):
        faults.append("under 24 GB of card memory")
    # torch's cu128 build, which the Blackwell cards need
    if spec.get("cuda") != "12.8":
        faults.append("not CUDA 12.8")
    return faults


@pytest.mark.spec("pod.session-spec-pins")
def test_the_session_spec_pins_the_recorded_image_and_bounds_the_spend():
    spec = tomllib.loads(GPUNIT_SPEC.read_text())
    assert spec_faults(spec, json.loads(IMAGE_CONFIG.read_text())) == []


@pytest.mark.spec_exempt("structural: twin of the session spec's pin check")
def test_the_spec_check_catches_a_tag_a_long_ceiling_and_a_missing_floor():
    config = {"image": "ghcr.io/a/b", "digest": "sha256:" + "0" * 64}
    good = {
        "image": "ghcr.io/a/b@sha256:" + "0" * 64,
        "ceiling": "45m",
        "volume": "v",
        "vram_gb": 24,
        "cuda": "12.8",
    }
    assert spec_faults(good, config) == []
    assert spec_faults({**good, "image": "ghcr.io/a/b:latest"}, config) == [
        "not config/image.json's pin"
    ]
    assert spec_faults(good, {"image": "ghcr.io/a/b", "digest": "latest"}) == [
        "not config/image.json's pin"
    ]
    assert spec_faults({**good, "ceiling": "1h"}, config) == ["no ceiling within 45 minutes"]
    assert spec_faults({**good, "ceiling": "45"}, config) == ["no ceiling within 45 minutes"]
    bare = {"image": good["image"], "ceiling": "45m", "vram_gb": 16}
    assert spec_faults(bare, config) == [
        "no volume",
        "under 24 GB of card memory",
        "not CUDA 12.8",
    ]


@pytest.mark.spec("pod.pins-face-deps")
def test_dockerfile_installs_requests():
    # ComfyUI imports `requests` (app/frontend_management.py) but does NOT declare it
    # in its requirements.txt — the minimal CUDA base lacks it, so ComfyUI crashes at
    # startup with ModuleNotFoundError unless we install it explicitly.
    assert "requests" in DOCKERFILE.read_text()


def launch_faults(dockerfile: str, pyproject: str) -> list[str]:
    """Return how the image misses starting through gpunit's boot script into the start module.

    e.g. a build file whose only command is `CMD ["/opt/start.sh"]` -> every fault
    """
    faults = []
    tag = re.search(r'gpunit@(v[0-9][^"]*)', pyproject)
    boot = f"https://raw.githubusercontent.com/alxb1t/gpunit/{tag[1] if tag else '-'}/boot/boot.sh"
    added = re.compile(
        rf"^ADD --checksum=sha256:[0-9a-f]{{64}} \\\n\s+{re.escape(boot)} /opt/gpunit/boot.sh$",
        re.M,
    )
    if not added.search(dockerfile):
        faults.append("boot.sh added at gpunit's pinned tag with a checksum")
    if not re.search(r'^ENTRYPOINT \["/opt/gpunit/boot.sh", "--"\]$', dockerfile, re.M):
        faults.append("boot.sh as the entry point")
    if not re.search(r'^CMD \["python3", "/opt/sp/pod_start.py"\]$', dockerfile, re.M):
        faults.append("the start module as the command")
    if "COPY synthetic_portraits/pod_start.py /opt/sp/pod_start.py" not in dockerfile:
        faults.append("the start module copied in")
    return faults


@pytest.mark.spec("pod.launches-via-start")
def test_the_image_starts_through_gpunits_boot_script_into_the_start_module():
    pyproject = (REPO_ROOT / "pyproject.toml").read_text()
    assert launch_faults(DOCKERFILE.read_text(), pyproject) == []


@pytest.mark.spec_exempt("structural: twin of the image's launch check")
def test_the_launch_check_catches_a_shell_start_and_a_boot_script_at_another_tag():
    pyproject = '"gpunit @ git+https://github.com/alxb1t/gpunit@v0.2.0",'
    assert launch_faults('CMD ["/opt/start.sh"]\n', pyproject) == [
        "boot.sh added at gpunit's pinned tag with a checksum",
        "boot.sh as the entry point",
        "the start module as the command",
        "the start module copied in",
    ]
    moved = DOCKERFILE.read_text().replace("gpunit/v0.2.0/", "gpunit/v0.1.0/")
    assert launch_faults(moved, pyproject) == [
        "boot.sh added at gpunit's pinned tag with a checksum"
    ]


# The switches the pod's libraries read, each set to turn its report or check off.
TELEMETRY_OFF = {
    "ORT_DISABLE_TELEMETRY": "1",
    "HF_HUB_DISABLE_TELEMETRY": "1",
    "NO_ALBUMENTATIONS_UPDATE": "1",
    "DO_NOT_TRACK": "1",
}


def telemetry_left_on(dockerfile: str) -> list[str]:
    """Return each telemetry switch the build file's `ENV` lines do not turn off."""
    set_to: dict[str, str] = {}
    for line in dockerfile.splitlines():
        if line.startswith("ENV "):
            for pair in line[4:].split():
                name, _, value = pair.partition("=")
                set_to[name] = value
    return [name for name, off in TELEMETRY_OFF.items() if set_to.get(name) != off]


@pytest.mark.spec("pod.telemetry-off")
def test_the_image_turns_its_libraries_telemetry_off():
    assert telemetry_left_on(DOCKERFILE.read_text()) == []


@pytest.mark.spec_exempt("structural: twin of the image's telemetry check")
def test_the_telemetry_check_catches_a_switch_left_out_or_left_on():
    assert telemetry_left_on("ENV ORT_DISABLE_TELEMETRY=0 HF_HUB_DISABLE_TELEMETRY=1\n") == [
        "ORT_DISABLE_TELEMETRY",
        "NO_ALBUMENTATIONS_UPDATE",
        "DO_NOT_TRACK",
    ]


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
