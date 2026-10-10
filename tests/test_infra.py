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

from tools.image_record import copied, record

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


def unpinned_sources(dockerfile: str) -> list[str]:
    """Return each `FROM` with no digest and each `ADD` of a URL with no checksum.

    e.g. "FROM ubuntu:22.04" -> ["FROM ubuntu:22.04"]
    """
    joined = re.sub(r"\\\n\s*", " ", dockerfile)
    found = []
    for line in joined.splitlines():
        if re.match(r"FROM\s", line) and not re.search(r"@sha256:[0-9a-f]{64}\b", line):
            found.append(line)
        if re.match(r"ADD\s", line) and "://" in line and "--checksum=sha256:" not in line:
            found.append(line)
    return found


@pytest.mark.spec("pod.pins-base-by-digest")
def test_every_image_built_from_carries_a_digest_and_every_url_a_checksum():
    text = DOCKERFILE.read_text()
    assert re.search(r"^FROM \S+@sha256:", text, re.M), "the build file names no base"
    assert unpinned_sources(text) == []


@pytest.mark.spec_exempt("structural: twin of the base-image digest check")
def test_the_digest_check_catches_a_tag_and_an_unchecked_download():
    assert unpinned_sources(
        "FROM ubuntu:22.04\n"
        f"FROM ubuntu@sha256:{'a' * 64} AS ok\n"
        "ADD https://example.org/boot.sh /boot.sh\n"
        f"ADD --checksum=sha256:{'b' * 64} \\\n    https://example.org/ok.sh /ok.sh\n"
    ) == ["FROM ubuntu:22.04", "ADD https://example.org/boot.sh /boot.sh"]


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


# --- The image is built on request and recorded (change 0006, design D9) -----------


def workflow_faults(workflow: str) -> list[str]:
    """Return how the image workflow misses being built on request only, unpruned, by SHA.

    e.g. a workflow triggered `on: push` -> ["a manual request its only trigger", ...]
    """
    faults = []
    triggers = re.search(r"^on:\n((?:[ \t]+.*\n|\n)*)", workflow, re.M)
    events = re.findall(r"^  (\w+):", triggers[1], re.M) if triggers else []
    if events != ["workflow_dispatch"]:
        faults.append("a manual request its only trigger")
    if not re.search(r"^\s+tag:\n(?:\s+.*\n)*?\s+required: true$", workflow, re.M):
        faults.append("a required tag")
    if not re.search(r'if \[ "\$REQUESTED" = "latest" \]; then\n\s+echo .*\n\s+exit 1', workflow):
        faults.append("latest refused")
    if "delete-package-versions" in workflow:
        faults.append("no registry version deleted")
    for action in re.findall(r"uses:\s*(\S+)", workflow):
        if not re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40}", action):
            faults.append(f"{action} pinned by commit SHA")
    return faults


@pytest.mark.spec("pod.image-built-on-request")
def test_the_image_is_built_only_on_request_and_never_pruned():
    assert workflow_faults(BUILD_IMAGE.read_text()) == []


@pytest.mark.spec_exempt("structural: twin of the image workflow's trigger check")
def test_the_workflow_check_catches_a_push_trigger_a_prune_and_a_moving_tag():
    pruning = (
        "on:\n  workflow_dispatch:\n  push:\n    branches: [main]\n\njobs:\n  b:\n    steps:\n"
        "      - uses: actions/checkout@v4\n"
        "      - uses: actions/delete-package-versions@v5\n"
    )
    assert workflow_faults(pruning) == [
        "a manual request its only trigger",
        "a required tag",
        "latest refused",
        "no registry version deleted",
        "actions/checkout@v4 pinned by commit SHA",
        "actions/delete-package-versions@v5 pinned by commit SHA",
    ]


def record_faults(config: Mapping[str, object], derived: Mapping[str, str]) -> list[str]:
    """Return each path whose recorded SHA-256 departs from the tree's, sorted.

    e.g. {"files": {"Dockerfile": "<old>"}} beside a changed `Dockerfile` -> ["Dockerfile"]
    """
    files = config.get("files")
    if not isinstance(files, dict):
        return ["config/image.json records no files"]
    names = sorted({str(name) for name in files} | set(derived))
    return [name for name in names if files.get(name) != derived.get(name)]


@pytest.mark.spec("pod.image-record-matches-the-tree")
def test_the_build_record_agrees_with_the_tree():
    derived = record()
    assert {
        "Dockerfile",
        "constraints.txt",
        "synthetic_portraits/pod_start.py",
        "synthetic_portraits/provision.py",
        "config/models.json",
    } <= set(derived)
    assert record_faults(json.loads(IMAGE_CONFIG.read_text()), derived) == []


@pytest.mark.spec_exempt("structural: twin of test_the_build_record_agrees_with_the_tree")
def test_the_record_check_catches_a_file_edited_after_the_record(tmp_path: Path):
    (tmp_path / "Dockerfile").write_text("FROM x\nCOPY a.py /a.py\n")
    (tmp_path / "a.py").write_text("one\n")
    config: dict[str, object] = {"files": record(tmp_path)}
    assert record_faults(config, record(tmp_path)) == []
    (tmp_path / "a.py").write_text("two\n")
    assert record_faults(config, record(tmp_path)) == ["a.py"]
    (tmp_path / "Dockerfile").write_text("FROM x\nCOPY a.py /a.py\nCOPY b.py /b.py\n")
    (tmp_path / "b.py").write_text("")
    assert record_faults(config, record(tmp_path)) == ["Dockerfile", "a.py", "b.py"]
    assert record_faults({}, record(tmp_path)) == ["config/image.json records no files"]


@pytest.mark.spec("pod.image-record-matches-the-tree")
@pytest.mark.parametrize(
    "line",
    [
        "COPY --chmod=755 a.py /a.py",
        "COPY a.py b.py /opt/",
        "ADD a.py /a.py",
        "add a.py /a.py",
        "ADD https://example.org/a.py /a.py",
    ],
)
def test_the_record_refuses_a_copy_it_cannot_read(line: str):
    with pytest.raises(ValueError, match=re.escape(repr(line))):
        copied(f"FROM x\nCOPY ok.py /ok.py\n{line}\n")


@pytest.mark.spec("pod.image-record-matches-the-tree")
def test_the_record_reads_past_a_checksummed_url_and_an_image_copy():
    dockerfile = (
        "FROM x\nCOPY a.py /a.py\n"
        f"ADD --checksum=sha256:{'0' * 64} \\\n    https://example.org/b /b\n"
        "COPY --from=builder /c /c\n"
    )
    assert copied(dockerfile) == ["a.py"]


def unprinted_record(workflow: str) -> list[str]:
    """Return what the workflow's summary lacks of the digest and the build record."""
    faults = []
    if not re.search(r"\$\{\{ steps\.build\.outputs\.digest \}\}", workflow):
        faults.append("the digest")
    printed = re.search(
        r"python3 tools/image_record\.py\n(?:.*\n)*?.*>> \"\$GITHUB_STEP_SUMMARY\"", workflow
    )
    if not printed:
        faults.append("the build record")
    checkout = workflow.find("actions/checkout@")
    if checkout < 0 or (printed and checkout > printed.start()):
        faults.append("its own checkout first")
    return faults


@pytest.mark.spec("pod.image-workflow-prints-the-record")
def test_the_workflow_prints_the_digest_and_the_build_record():
    assert unprinted_record(BUILD_IMAGE.read_text()) == []


@pytest.mark.spec_exempt("structural: twin of the workflow's record check")
def test_the_record_print_check_catches_a_summary_without_the_record():
    assert unprinted_record("steps:\n  - run: echo hi\n") == [
        "the digest",
        "the build record",
        "its own checkout first",
    ]


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
