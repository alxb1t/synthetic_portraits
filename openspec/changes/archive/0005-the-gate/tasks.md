# Tasks — 0005-the-gate

Declare once, then prose. [design](design.md) is authoritative for how; each phase ends on a green gate.

## Progress

- [x] 1 — Declare once
- [x] 2 — Prose

## 1 — Declare once

The `Makefile` becomes the one declaration; the toml and its test go together ([D8](design.md#d8)).

- [x] 1.1 Rewrite `Makefile`'s header and add a column-0 comment above each command, per [D1](design.md#d1).
      Verify: `make -n gate` prints exactly `uv sync --locked`, `uv run ruff format --check .`,
      `uv run ruff check .`, `uv run ty check`, `uv run pytest -q`, one a line, and no `#` line.
- [x] 1.2 Delete `.minions/minions.toml` with `git rm`, per [D1](design.md#d1).
      Verify: `git ls-files .minions` prints nothing.
- [x] 1.3 Delete `tests/test_gate_mirrors.py` with `git rm`, as [D3](design.md#d3) authorizes.
      Verify: `test ! -e tests/test_gate_mirrors.py` exits 0.
- [x] 1.4 Replace `.github/workflows/ci.yml:21-35` with the one `Gate` step, and delete `:3-5`, per
      [D2](design.md#d2). Verify: `grep -c 'run:' .github/workflows/ci.yml` prints `1`, and
      `grep -c 'run: make gate' .github/workflows/ci.yml` prints `1`.
- [x] 1.5 Replace `.gitignore:10-13` with the lines in [D5](design.md#d5).
      Verify: `grep -c '^\.minions/$' .gitignore` prints `1`, and `grep -c 'minions.toml' .gitignore` prints `0`.

## 2 — Prose

`CLAUDE.md` and `README.md` point at the `Makefile` and list no command ([D4](design.md#d4)).

- [x] 2.1 Rewrite `CLAUDE.md:18-34`, `:88-91` and `:103` per [D4](design.md#d4).
      Verify: `grep -c 'uv run\|uv sync\|array\|minions.toml' CLAUDE.md` prints `0`, and
      `grep -c 'make -n gate' CLAUDE.md` prints `1`.
- [x] 2.2 Rewrite `README.md:129-145` per [D4](design.md#d4).
      Verify: `grep -c 'array\|minions.toml\|gate_mirrors' README.md` prints `0`, and
      `grep -c 'make -n gate' README.md` prints `1`.
- [x] 2.3 **HALT CHECK** — no copy survives outside history.
      Verify: `grep -rln 'minions.toml\|gate_mirrors' . --exclude-dir=.git --exclude-dir=.venv --exclude-dir=.minions --exclude-dir=openspec --exclude-dir=.pytest_cache --exclude-dir=__pycache__ --exclude=CHANGELOG.md`
      prints nothing.
