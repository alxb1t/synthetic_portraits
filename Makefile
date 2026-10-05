# The gate: this recipe is its one declaration. CI and the MinionsFactory skills run
# `make gate`; `make -n gate` prints what it runs.

.PHONY: gate

gate:
# the environment: certifies what uv.lock pins, not whatever .venv holds
	uv sync --locked
# format, in check mode (a formatter in rewrite mode is not the check)
	uv run ruff format --check .
# lint: E,F,I,UP,B,SIM,D,ANN; tests/** exempt from D1, D401 and ANN
	uv run ruff check .
# strict types
	uv run ty check
# the suite, offline and deterministic
	uv run pytest -q
