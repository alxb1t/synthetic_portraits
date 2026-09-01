# Tasks — 0003-mf-standards

Six phases. Each is independently committable, ends on a **green gate**, a `CHANGELOG` entry (from
phase 5 onward, when the file exists), a ticked `## Progress` box and **one** commit whose message ends
with a `Change: 0003-mf-standards` trailer contiguous with any `Co-Authored-By:` line.

`design.md` is authoritative for *how*; it is not re-derived here. **The order of phases 1→2 is
load-bearing** (design D6): the gate array is declared before `CLAUDE.md` quotes it.

Until phase 1 lands there is no `make gate`; run the five commands directly. From phase 1 onward,
**the gate is `make gate`, run and never summarized.**

## Progress

- [x] 1 — The declared gate: `minions.toml`, `Makefile`, CI, lint selectors
- [x] 2 — `CLAUDE.md`: rewritten to the template
- [x] 3 — Cut the vault coupling, and guard it with a test
- [x] 4 — `openspec/config.yaml`: the authoring context
- [x] 5 — `CHANGELOG.md` and the version line
- [ ] 6 — `README.md`, and the whole-change verification

---

## 1. The declared gate

The single source of truth for "done", plus two of its four mirrors (`Makefile`, `ci.yml`), in **one
commit** so a reviewer can diff them side by side (design D1, and the drift risk). `CLAUDE.md` mirrors it
in phase 2 and `README.md` in phase 6.

- [x] 1.1 Write `.minions/minions.toml` with the ordered `gate` array — `uv sync --locked`,
      `ruff format --check .`, `ruff check .`, `ty check`, `pytest -q`. Verify:
      `uv run python -c "import tomllib,pathlib;print(tomllib.loads(pathlib.Path('.minions/minions.toml').read_text())['gate'])"`
      prints exactly those five, in that order.
- [x] 1.2 Add `.minions/*` then `!.minions/minions.toml` to `.gitignore`. Verify **on file paths, not the
      directory** — `git check-ignore -q .minions/findings/x_review.md` exits 0 **and**
      `git check-ignore -q .minions/minions.toml` exits 1.
- [x] 1.3 Add a `Makefile` with a `gate` target mirroring the array command-for-command, each prefixed
      `uv run` where the array names a tool. Verify: `make gate` exits 0, and the target's commands read
      in the same order as `minions.toml`.
- [x] 1.4 Add `.python-version` pinning one interpreter consistent with `requires-python = ">=3.11"`.
      Verify: `uv run python -V` reports that version.
- [x] 1.5 In `pyproject.toml`: add `D` and `ANN` to `[tool.ruff.lint] select`; add a `per-file-ignores`
      entry scoping `D1*`, `D401` and `ANN*` out of `tests/**`; ignore `D203` and `D213` (design D2's two
      incompatible pairs); register `markers = ["spec", "spec_exempt"]` under
      `[tool.pytest.ini_options]`. Verify: `uv run pytest --markers` lists both markers, and
      `uv run ruff check .` emits **no `warning:` line** (a merely-green run with warnings does not pass
      this task).
- [x] 1.6 Fix the **34** measured `D`/`ANN` violations in `synthetic_portraits/` (30) and `scripts/` (4)
      — real docstrings and honest annotations, no blanket `# noqa`. Verify: `uv run ruff check .` exits
      0 and `uv run pytest -q` still reports **120 passed** (corrected from 114 during phase 1:
      the original figure counted `def test_` and missed parametrization).
- [x] 1.7 Rewrite `.github/workflows/ci.yml` as one step per array command, in array order —
      `uv sync` becomes `uv sync --locked`, and `ruff format --check .` is added. Verify: the workflow's
      `run:` lines, read top to bottom, equal the array.
- [x] 1.8 Refresh `uv.lock` and commit it in this phase — the tracked lock currently records
      `version = "0.1.0"` against a `pyproject` of `0.2.0`, so `uv sync --locked` **fails on the tree as
      it stands** (measured 2026-09-01). Verify: `uv sync --locked` exits 0.

## 2. `CLAUDE.md` — rewritten to the template

Second, not first, and deliberately so — design D6. It quotes the array from phase 1; written earlier it
would document a gate no file declares. This repo writes **no `docs/sdd.md`** (design D10), so this file
carries the change-cutting facts and points at the tools for the rest.

- [x] 2.1 Rewrite `CLAUDE.md` whole from the template: the one-paragraph what-it-is, the gate **quoted
      from the array**, the seams, the engineering conventions, `## How a change is cut here` (scaffold →
      author → validate, with the OpenSpec version and the `Change:` trailer rule), the guardrails, and
      the layout. Verify: no unfilled template placeholder remains **in prose** —
      `sed 's/`[^`]*`//g' CLAUDE.md | grep -c '<[a-z-]\+>'` is 0 — and `wc -l CLAUDE.md` is **≤ 120**
      (target ~100). The check strips code spans first: angle brackets inside backticks are command
      metasyntax (`openspec new change <NNNN-slug>`), which the CLAUDE.md template itself ships, so the
      unstripped grep this task originally specified could never pass. Corrected during phase 2.
- [x] 2.2 Point at the tools for the method rather than restating it (design D10): `openspec instructions
      <artifact>` owns artifact structure, and the `mf-build` / `mf-converge` / `mf-release` /
      `mf-backlog-export` skills own the build, check, converge and release loop. Name them; do **not**
      restate the loop, the findings contract or the release fold. Verify: `CLAUDE.md` names all four
      skills and contains no restatement of the findings contract.
- [x] 2.3 In the gate section, record why `docker build --check` is **not** in the array (design D1), so
      its absence reads as a decision rather than an oversight. Verify:
      `grep -c 'docker build --check' CLAUDE.md` is at least 1.
- [x] 2.4 Remove the "plan lives in a private vault" section and every method restatement, leaving facts
      only — no numbered "first do X" ritual. Verify: `grep -ci 'vault\|implementation_plan' CLAUDE.md`
      is 0.
- [x] 2.5 Confirm every directory named in the layout section exists — this change creates **no**
      `docs/` tree (deferred), so the layout must not name one — and that the five gate lines match
      `.minions/minions.toml`. Verify: each path in the layout resolves on disk; the gate lines diff
      clean against the array.
- [x] 2.6 Do **not** create `AGENTS.md` (design D7 — edit whichever exists, never write both). Verify:
      `test ! -e AGENTS.md`.

## 3. Cut the vault coupling, and guard it with a test

Test-first: 3.1 is written red, before the edits that make it green.

- [x] 3.1 Add `tests/test_repo_hygiene.py` asserting that no tracked file (excluding `.env`, which is
      gitignored) contains `VAULT_PROJECT_DIR`, an absolute `/Users/` path, or any other real absolute
      path from the host. Enumerate via `git ls-files`, so the assertion covers the tracked set rather
      than a hand-listed one. Verify: the test **fails** on the current tree naming the known sites, then
      passes after 3.2–3.3.
- [x] 3.2 Remove `VAULT_PROJECT_DIR` from `.env.example`, leaving it path-free and declaring shape only.
      Verify: `grep -c VAULT .env.example` is 0, and the remaining keys carry no value from this machine.
- [x] 3.3 Remove the vault reference from `synthetic_portraits/__init__.py`'s module docstring. Verify:
      `grep -rin vault -- $(git ls-files ':!openspec/*')` returns nothing.
- [x] 3.4 Confirm the repo resolves no path outside itself. Verify: `test_repo_hygiene.py` passes and the
      full gate is green.

## 4. `openspec/config.yaml` — the authoring context

- [x] 4.1 Fill `context:` as a **pointer** — `CLAUDE.md` for this repo's facts and its change-cutting
      section, not restated, the page winning where they disagree. Verify: the block contains no copy of
      the gate array and no restatement of the loop.
- [x] 4.2 Fill `rules:` for `proposal`, `specs`, `design` and `tasks` with only what an author cannot
      derive from `CLAUDE.md` — including the `skip_specs` + `.gitkeep` pairing, one `spec.md` per
      capability directory, "never invent a requirement", "record the measurement behind each decision",
      and the phase/`## Progress` task format this repo's builder parses. Verify:
      `openspec validate --all --strict` exits 0.

## 5. `CHANGELOG.md` and the version line

- [x] 5.1 Create `CHANGELOG.md` in Keep a Changelog + SemVer form, backfilling `## [0.2.0]` and
      `## [0.1.0]` from the existing annotated tags, and opening `## [Unreleased]` with one entry per
      phase already built (1–4). Verify: both released sections exist with their tag dates, and
      `## [Unreleased]` names phases 1–4.
- [x] 5.2 Bump `pyproject.toml` `version` `0.2.0` → `0.3.0` (design D8) and refresh `uv.lock`. Verify:
      the version file, `proposal.md`'s `version: v0.3` and the `## [Unreleased]` heading-to-be all agree;
      `uv sync --locked` exits 0. The **tag is not created here** — `mf-release` cuts it.

## 6. `README.md`, and the whole-change verification

- [ ] 6.1 Add a gate section to `README.md` stating `make gate` and the five commands in array order, and
      refresh "current status" to v0.3. Verify: the five commands appear in order, and no stale v0.2
      status line remains.
- [ ] 6.2 Diff the array against its four mirrors by eye — `.minions/minions.toml` (the source) against
      `Makefile`, `ci.yml`, `README.md` and `CLAUDE.md`. Verify: all five files carry the same commands in
      the same order.
- [ ] 6.3 Run the whole gate and the validator, and report the output rather than summarizing it. Verify:
      `make gate` exits 0 with **at least 121 passed** (120 + the guard test(s) from phase 3), and
      `openspec validate --all --strict` exits 0.
- [ ] 6.4 Confirm every commit of this change carries its trailer. Verify:
      `git log --grep "Change: 0003-mf-standards" --oneline | wc -l` equals the number of phase commits,
      and `git log -1 --format=%B` shows the trailer contiguous with `Co-Authored-By:`.
