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

**None — this change adds no behaviour, and declares the absence rather than inventing a requirement
to satisfy the validator: `skip_specs: true` in this change's `.openspec.yaml`, with
`specs/.gitkeep`.**

It does, however, **seed the living spec tree**. Phase 7 backfills `openspec/specs/` with the
behaviour that already exists, so the tree this change adopts ships populated rather than empty
(design D12; placed in the living tree rather than cut as a delta by D14, 2026-09-02). That is
documentation of current functionality, not a change to it — which is why it is written directly as
`## Requirements` in `openspec/specs/<capability>/spec.md` and why this change still carries no
delta. Seven capabilities, enumerated from the test suite and the CLI surface rather than from the
module layout, each proved by tests that already pass:

- `portrait-generation` — a text prompt becomes a photoreal image written to disk, with framing,
  seed and count under the caller's control.
- `face-detectability` — every delivered image holds exactly one detectable face, enforced by a
  bounded regenerate loop and assertable offline over any image set.
- `identity-preserving-generation` — a reference face renders the same synthetic person across
  many prompts.
- `batch-generation` — a file of prompts renders a whole set in one invocation, under stable,
  sortable filenames.
- `model-selection` — the generation model is chosen by registered name, with an unusable choice
  rejected locally rather than at paid GPU time.
- `comfyui-execution` — renders are queued, awaited and fetched across a substitutable seam, with
  every server failure surfaced as an error rather than a hang.
- `gpu-pod-provisioning` — the GPU pod is built, provisioned and torn down reproducibly, with every
  model file verified before use.

No behaviour changes and no test's meaning changes: 100 scenarios describe what the code already
does, each bound to a proving test by a `spec` marker. Design D13 records the capability-to-test map,
the layer vocabulary and the four coverage gaps left open rather than specified.

### Modified Capabilities

None. `openspec/specs/` is empty at the start of this change and holds the seven capabilities above
at its end — none of them a requirement this change altered.

## Impact

**Added:** `.minions/minions.toml` · `Makefile` · `.python-version` · `CHANGELOG.md` · `openspec/`
(config, changes, and the seeded `specs/` tree — seven capabilities, 29 requirements, 100 scenarios).

**Modified:** `CLAUDE.md` (rewritten) · `.github/workflows/ci.yml` (mirrors the array) · `.gitignore` ·
`.env.example` (loses `VAULT_PROJECT_DIR`) · `README.md` (states the gate) · `pyproject.toml` (ruff
selectors, registered `spec` / `spec_exempt` markers, version → `0.3.0`).

**Runtime code:** `synthetic_portraits/` and `scripts/` gain docstrings and type annotations to satisfy
the new selectors — **34 violations, measured 2026-09-01**. No behavioural change, no signature change,
no new runtime dependency. The stdlib-only guardrail and the sanctioned `faces` extra are untouched.

**Tests:** unchanged in behaviour. The suite stays offline and deterministic, and passes at every
phase boundary — 120 tests at the cut, 132 once phases 3 and 5 add their guards. Phase 7 adds only
`spec` markers; it deletes, skips and rewrites nothing.

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
- **Building the spec↔test binding checker.** Phase 7 writes the binding — every scenario `Key:`
  carries a `spec` marker on a proving test — but no checker enforces it and the gate array gains no
  binding entry. The standard grades the checker advisory (design D4, unchanged by D12).
- **Migrating the vault's draft `v0.3_implementation_plan.md`.** It renumbers to v0.4 and is cut as an
  openspec change then.
- **Any change to the GPU pipeline, the image, or the generated output.**
- **Merging, pushing or tagging.** Those are the human's.
