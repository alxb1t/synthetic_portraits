"""The declared gate array and its four mirrors say the same thing.

`.minions/minions.toml` holds the `gate` array — the single source of truth for what "done"
means here. Four files restate it: `Makefile`, `.github/workflows/ci.yml`, `README.md` and
`CLAUDE.md`. Nothing but this module checks that they agree, and a drifted mirror documents
a gate the repository does not run.

The array is stored in **executable form**, exactly as a shell runs each command, so every
comparison below is a plain string equality rather than a comparison plus an unwritten
"prepend the runner" rule. That shape is what makes this test worth having: a mirror check
that had to encode a prefix convention would just move the convention from prose into code.
"""

from __future__ import annotations

import re
import tomllib

from conftest import REPO_ROOT, STRUCTURAL_GUARD

pytestmark = STRUCTURAL_GUARD


def _gate() -> list[str]:
    data = tomllib.loads((REPO_ROOT / ".minions/minions.toml").read_text())
    return data["gate"]


def _makefile_recipe() -> list[str]:
    lines = (REPO_ROOT / "Makefile").read_text().splitlines()
    start = lines.index("gate:") + 1
    return [ln[1:] for ln in lines[start:] if ln.startswith("\t")]


def _ci_run_steps() -> list[str]:
    text = (REPO_ROOT / ".github/workflows/ci.yml").read_text()
    return re.findall(r"^\s+run: (.+)$", text, flags=re.MULTILINE)


def _readme_block() -> list[str]:
    text = (REPO_ROOT / "README.md").read_text()
    for block in re.findall(r"```bash\n(.*?)```", text, flags=re.DOTALL):
        lines = [ln for ln in block.splitlines() if ln.strip()]
        if lines and lines[0].startswith("uv sync"):
            return lines
    return []


def _claude_bullets() -> list[str]:
    text = (REPO_ROOT / "CLAUDE.md").read_text()
    return re.findall(r"^- `(uv [^`]+)` — ", text, flags=re.MULTILINE)


def test_the_declared_gate_is_a_non_empty_ordered_array():
    assert _gate() == [
        "uv sync --locked",
        "uv run ruff format --check .",
        "uv run ruff check .",
        "uv run ty check",
        "uv run pytest -q",
    ]


def test_the_makefile_gate_target_mirrors_the_array():
    assert _makefile_recipe() == _gate()


def test_the_ci_workflow_runs_one_step_per_array_command_in_order():
    assert _ci_run_steps() == _gate()


def test_the_readme_states_the_array_verbatim():
    assert _readme_block() == _gate()


def test_the_claude_context_file_quotes_the_array_verbatim():
    assert _claude_bullets() == _gate()
