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

SHELL_SCRIPTS = [DOWNLOAD, START]


def test_infra_files_exist():
    for path in [DOCKERFILE, DOWNLOAD, START]:
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
