---
version: v0.3
---

## Why

This repository's method lives in three places that cannot be checked against each other: a private
Obsidian vault holds the implementation plan of record, `CLAUDE.md` restates a paraphrased quality gate,
and `ci.yml` runs a third, shorter list. Nothing on disk says which is authoritative, so "where does the
work stand" and "what does done mean" are both answered from memory or from a path outside the repo.

Adopting the MinionsFactory repo standard replaces all three with one rule: **every claim about the work
has a place on disk where it can be checked, by a reader with no context but this repository.** Now,
because v0.3 is the first version whose work has not already been planned in the vault — cutting it as an
in-repo change is cheaper than migrating one mid-flight.

## What Changes

- **The gate becomes declared, not prose.** `.minions/minions.toml` carries the ordered `gate` array as
  the single source of truth; `Makefile`'s `gate` target, `.github/workflows/ci.yml` and `README.md`
  mirror it command-for-command. The array gains the two axes the repo claims but does not run in CI:
  `uv sync --locked` (the lock is currently uncertified — CI runs bare `uv sync`) and
  `ruff format --check .`.
- **Lint gains the standard's `D` and `ANN` selectors** on runtime code, with a measured, recorded
  exemption for `tests/**`.
- **`CLAUDE.md` is rewritten to the template** — facts only, the gate quoted from the declared array, and
  a `## How a change is cut here` section. It points at the tools for the rest of the method
  (`openspec instructions` for artifact structure; the `mf-*` skills for build, check, converge and
  release) rather than restating any of it.
- **BREAKING (workflow, not code): the repo stops resolving any path outside itself.**
  `VAULT_PROJECT_DIR` is removed from `.env.example` and from `CLAUDE.md`. The plan of record moves
  in-repo to `openspec/changes/`. The vault keeps intent and investigation and reads the repo one-way; the
  repo never reaches back.
- **`CHANGELOG.md` is added**, Keep a Changelog + SemVer, backfilled from the existing `v0.1.0` and
  `v0.2.0` tags, with entries appended per phase from this change onward.
- **`openspec/` is adopted** — `config.yaml` whose `context:` points at `CLAUDE.md` rather than restating
  it, plus the living `specs/` and `changes/` trees.
- **Every commit from this change onward carries a `Change: <change-id>` git trailer**, contiguous with
  any `Co-Authored-By:` line.
- **`.python-version` is added** and `.gitignore` gains `.minions/*` + `!.minions/minions.toml`.

## Capabilities

### New Capabilities

None. This change adds no behaviour to the pipeline: it declares how the work is defined, built and
checked. Per the standard, a change with no behavioural consequence **declares the absence** rather than
inventing a requirement to satisfy the validator — `skip_specs: true` in this change's `.openspec.yaml`,
with `specs/.gitkeep`.

### Modified Capabilities

None. `openspec/specs/` is empty at the start of this change and is empty at its end.

## Impact

**Added:** `.minions/minions.toml` · `Makefile` · `.python-version` · `CHANGELOG.md` · `openspec/`
(config, specs, changes).

**Modified:** `CLAUDE.md` (rewritten) · `.github/workflows/ci.yml` (mirrors the array) · `.gitignore` ·
`.env.example` (loses `VAULT_PROJECT_DIR`) · `README.md` (states the gate) · `pyproject.toml` (ruff
selectors, registered `spec` / `spec_exempt` markers, version → `0.3.0`).

**Runtime code:** `synthetic_portraits/` and `scripts/` gain docstrings and type annotations to satisfy
the new selectors — **34 violations, measured 2026-09-01**. No behavioural change, no signature change,
no new runtime dependency. The stdlib-only guardrail and the sanctioned `faces` extra are untouched.

**Tests:** unchanged in behaviour. The suite stays offline and deterministic; all 120 tests keep passing
at every phase boundary.

**Dependencies:** none added. The OpenSpec CLI is operator tooling resolved on `PATH`
(`@fission-ai/openspec@1.11.0`), deliberately outside the gate array so a moving version can never turn
CI red.

**Not affected:** `Dockerfile`, `infra/`, `workflows/`, `download_models.sh`, `generate.py` behaviour, and
the GPU pipeline itself. No phase of this change spends money.

## Non-goals

- **A `docs/sdd.md` method page.** The repo standard grades it required; this repo deliberately omits it
  (design D10). OpenSpec's own `instructions` own artifact structure and the `mf-*` skills carry the loop,
  so an in-tree restatement would be a fourth copy to drift. `CLAUDE.md`'s `## How a change is cut here`
  is the whole in-repo statement of method. **Recorded as a deviation from the standard, not an
  oversight.**
- **A `docs/` tree — the repo's own architecture map.** `docs/README.md` and `docs/modules/` were scoped
  into this change and deferred by the human on 2026-09-01, to be done as their own change. Until then
  `CLAUDE.md` and `README.md` are the repo's only architecture record (design D11).
- **Backfilling `openspec/specs/` with the existing pipeline's behavioural requirements.** That is a
  separate, larger change — the standard splits bundles rather than growing them. Deferred to v0.4.
- **Building the spec↔test binding checker.** Markers are registered and reserved; no checker is written
  and the gate array carries no binding entry. Traceability from scenario to test stays prose until a
  spec tree exists to bind.
- **Migrating the vault's draft `v0.3_implementation_plan.md`.** It renumbers to v0.4 and is cut as an
  openspec change then.
- **Any change to the GPU pipeline, the image, or the generated output.**
- **Merging, pushing or tagging.** Those are the human's.
