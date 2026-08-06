"""Image-as-code guardrails (Phase 3).

Locks the conventions the plan calls out — the cu128 pin (Blackwell/sm_120), the model
download set, and shell-script syntax — as executable checks. No Docker build or network
here; ``docker build --check`` runs in the gate.
"""

from __future__ import annotations

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


def test_dockerfile_launches_via_start_script():
    text = DOCKERFILE.read_text()
    assert "start.sh" in text
    assert 'CMD ["/opt/start.sh"]' in text


def test_download_is_idempotent_and_omits_extra_models():
    text = DOWNLOAD.read_text()
    assert "RealVisXL_V5.0" in text
    assert "skip" in text.lower()  # skips files already present
    # Prompt-only pipeline: no ControlNet and no InstantID model is fetched (a mention in a
    # comment is fine — only the download URLs are checked).
    url_lines = [ln for ln in text.splitlines() if "https://" in ln]
    assert not any("instantid" in ln.lower() for ln in url_lines)
    assert not any("controlnet" in ln.lower() for ln in url_lines)


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
