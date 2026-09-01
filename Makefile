# The quality gate — the one command a human types.
#
# This target mirrors the `gate` array in `.minions/minions.toml` command-for-command.
# That array is the source of truth; this is one of its four mirrors
# (Makefile · .github/workflows/ci.yml · README.md · CLAUDE.md). Change one, change all four.

.PHONY: gate

gate:
	uv sync --locked
	uv run ruff format --check .
	uv run ruff check .
	uv run ty check
	uv run pytest -q
