# The quality gate — the one command a human types.
#
# These recipe lines mirror the `gate` array in `.minions/minions.toml` byte for byte.
# That array is the source of truth; this is one of its four mirrors
# (Makefile · .github/workflows/ci.yml · README.md · CLAUDE.md), and
# tests/test_gate_mirrors.py fails if any of them drifts from it.

.PHONY: gate

gate:
	uv sync --locked
	uv run ruff format --check .
	uv run ruff check .
	uv run ty check
	uv run pytest -q
