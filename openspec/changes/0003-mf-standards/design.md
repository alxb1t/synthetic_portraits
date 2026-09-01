## Context

See `proposal.md` — Why. The constraints that shape the approach, all measured on 2026-09-01 against
`HEAD = d297ddb`:

| measured | value |
|---|---|
| tests, all offline and passing | 114 across 10 files |
| `ruff format --check .` today | clean — 23 files already formatted |
| `ruff check .` today (`E,F,I,UP,B,SIM`) | clean |
| adding `D,ANN`: `synthetic_portraits/` | **30** violations |
| adding `D,ANN`: `scripts/` | **4** violations |
| adding `D,ANN`: `tests/` | **311** violations (114 `D103` + 114 `ANN201` + 73 `ANN001` + 10 other) |
| `generate.py` | 0 violations |
| code reading `VAULT_PROJECT_DIR` | **none** — 3 prose sites only (`CLAUDE.md`, `.env.example`, `synthetic_portraits/__init__.py` docstring) |
| OpenSpec CLI on `PATH` | `1.11.0` |
| existing tags | `v0.1.0`, `v0.2.0`; `pyproject` version `0.2.0` — the version line currently holds |
| `openspec/specs/` | empty (created by `init` in this change) |

Two existing facts do real work in the decisions below. **`bash -n` already runs inside the suite** —
`tests/test_infra.py` parametrizes every shell script through it, skipping only where `bash` is absent. And
**the Dockerfile is built for real on every push to `main`** by `.github/workflows/build-image.yml`, which
is strictly stronger evidence than `docker build --check`.

## Goals / Non-Goals

**Goals**

- One declared command list on disk that decides "done" — the array in `.minions/minions.toml`, plus
  exactly four mirrors (`Makefile`, `ci.yml`, `README.md`, `CLAUDE.md`) a reader can diff by eye.
- A repo that resolves no path outside itself, so it can be read, cloned and open-sourced with no external
  context.
- The method stated in exactly one place per concern, and pointed at from everywhere else — never
  restated (D10).

**Non-Goals** (design-level, beyond the proposal's)

- Making the gate cover every axis this repo cares about. The image axis is deliberately outside the array
  (D1).
- A gate that requires a running daemon, a network, or a GPU. The array must be runnable on any checkout,
  offline.
- Enforcing docstring/annotation style on the test suite (D2).

## Decisions

### D1 — The gate array is five commands; the image axis stays outside it

```
uv sync --locked        environment — not a quality axis, hence first
ruff format --check .   format
ruff check .            lint
ty check                strict types
pytest -q               tests
```

**Why this order.** Lock-sync leads so the rest certifies what `uv.lock` pins, not whatever `.venv`
happens to hold. Today CI runs bare `uv sync`, which will silently update the lock — the array's first
command closes that. The standard puts the binding check last; this repo has none (D4), so `pytest -q` is
the terminal entry.

**Why `docker build --check` and `bash -n` are not in it.** Measured, not assumed:

- `bash -n` is **already covered** — `tests/test_infra.py` runs it over every shell script, so `pytest -q`
  carries that axis. Adding it to the array a second time would document one check as two.
- `docker build --check` requires a running Docker daemon. On a dev machine with Docker stopped the array
  would fail for a reason unrelated to code quality, and the standard's floor rule ("never weaken the gate
  to pass") makes that expensive to live with — the pressure would be to make the step conditional, and *a
  command that reports without failing covers no axis*. Meanwhile `build-image.yml` already performs a
  **real build** on every push to `main`, which subsumes the lint.

*Alternative weighed:* a seven-command array including both. Rejected on the two measurements above —
it would restate one covered axis and make the array un-runnable offline. `docker build --check` remains a
phase-scoped check for image-as-code work, named as such in `CLAUDE.md`'s gate section with this
reasoning, so a future reader does not mistake its absence for an oversight.

*Trade-off accepted:* a Dockerfile syntax error is caught on push to `main` rather than by the local gate.
The v0.2 history shows image work is rare and always accompanied by `test_infra.py` assertions.

### D2 — `D` and `ANN` are enforced on runtime code; `tests/**` is exempted, by measurement

The standard's `select = ["E","F","I","D","ANN"]` costs **34** violations on runtime code and **311** on
tests — a 9:1 split. The 311 are almost entirely `D103` (a docstring on a test whose name already reads as
a behavioural sentence) and `ANN201`/`ANN001` (`-> None` on a test function, and types on pytest fixture
parameters).

**Decision:** keep the repo's existing `E,F,I,UP,B,SIM` and add `D,ANN`, with a `per-file-ignores` entry
scoping `D1*`, `D401` and `ANN` out of `tests/**`. The 34 runtime violations are fixed in the same phase,
so the selector lands green.

**Why.** The standard itself says tests are "named as behavioural sentences and double as documentation" —
a docstring restating the name is the redundancy the naming rule already prevents, and 114 `-> None`
annotations catch no defect this suite could have. Enforcing there would buy noise, and noise is what makes
a floor rule get bent later.

*Alternative weighed:* annotate and document all 311. Rejected — mechanical, ~300 diff lines through the
one part of the repo reviewers actually read, with no defect class closed. *Alternative weighed:* skip `D`
and `ANN` entirely. Rejected — the 34 runtime sites are exactly where a public docstring and a return type
carry their weight, and this is a library-shaped package with a `FaceDetector`/`ComfyTransport` facade
whose signatures are its contract.

**Two ruff incompatibilities must be resolved explicitly**, or every run prints a warning:
`D203`/`D211` and `D212`/`D213` are mutually exclusive pairs. This repo takes `D211` (no blank line before
class) and `D212` (multi-line summary on the first line), matching the existing docstrings, and ignores
`D203` + `D213` so the gate output is clean rather than merely green.

### D3 — This change declares `skip_specs: true`; the living specs are backfilled later

`openspec/specs/` is empty and stays empty. Adopting a method changes no behaviour, and the standard is
explicit: **never invent a requirement to satisfy the validator.** The mutually-exclusive combination that
passes is `skip_specs: true` **plus `specs/.gitkeep`** — a non-`.md` file, so the directory stays tracked
and no spec file exists. A `specs/README.md` saying "no delta" fails; so does omitting `skip_specs`.

*Alternative weighed:* backfill capability specs for the current pipeline in this change. Rejected on
size — 114 tests across 7 runtime modules is a change of its own, and bundling it would push this one past
the "around ten phases" ceiling. It is a named non-goal, deferred to v0.4.

### D4 — Markers are registered and reserved; no binding checker is written

`spec` and `spec_exempt` are registered in `[tool.pytest.ini_options] markers` so that an unregistered
marker can never be silently ignored later. No checker is built and the gate array carries no binding
entry.

**Why.** A binding check over an empty spec tree resolves zero scenarios, and *a station that checked zero
things reads exactly like a clean one* — the standard's own `empty` invariant, in tooling form. Registering
the markers now is free and prevents the one failure that is expensive to discover later (a marker that
binds nothing because pytest never knew the name). The checker is written when there is a spec tree for it
to bite on. The standard grades the binding check **advisory**, so this is a supported adoption state, not
a gap.

### D5 — The vault link is prose-only, so cutting it is a three-file edit

No code, test, or script reads `VAULT_PROJECT_DIR` — it appears in `CLAUDE.md`, `.env.example`, and one
docstring in `synthetic_portraits/__init__.py`. Cutting it needs no migration path and cannot break a run.

What replaces each function the vault was serving:

| the vault held | it now lives in |
|---|---|
| the implementation plan of record | `openspec/changes/<id>/` — four artifacts |
| "where are we" (`current_phase`, progress ledger) | the change's `tasks.md` `## Progress` + `git log --grep "Change: <id>"` |
| architecture, repo layout, conventions | `CLAUDE.md` only, until the deferred `docs/` change (D11) |
| the method / phase workflow contract | `CLAUDE.md` § How a change is cut here, plus the tools themselves (D10) |
| deferred work during a version | `.minions/<version>_backlog.md` |
| intent, investigation, chronology, decisions | **stays in the vault** — it reads the repo; the repo never reaches back |

The direction is the point: a repo that can reach a personal knowledge base cannot be safely
open-sourced, and this one is public.

### D6 — Phase order is gate → `CLAUDE.md`, and it cannot be otherwise

The human asked for `CLAUDE.md` first. It is placed **second**, because the template makes it derivative
of one artifact that must already exist: it quotes the gate *command-for-command from the declared array*.
Written first it would quote an array no file declares — documenting a gate the repo does not run, which
is the exact defect the standard's "quoted" rule exists to prevent. The standard's own adoption note
agrees: *"gate first ... a repo with no green gate has nothing for the rest to stand on."*

Dropping `docs/sdd.md` (D10) removed the change's second dependency and moved `CLAUDE.md` from third to
second — as early as it can honestly be written. This is recorded rather than silently applied, because
it overrides a direct instruction.

### D7 — `CLAUDE.md` is edited; `AGENTS.md` is never created

The repo has `CLAUDE.md`. The standard's rule is: edit whichever exists, and **never write both**. No
`AGENTS.md` is added.

### D8 — The version file is bumped once, in the CHANGELOG phase

`pyproject.toml` goes `0.2.0` → `0.3.0` in the same commit that creates `CHANGELOG.md`, so the four-way
version line (`proposal.md: version: v0.3` = `CHANGELOG ## [0.3.0]` = `pyproject 0.3.0` = tag `v0.3.0`)
is assembled in one place and can be checked by eye from that commit onward. The tag is not created here —
`mf-release` cuts it, and merge and push stay the human's.

### D9 — OpenSpec is operator tooling, recorded and not pinned

`@fission-ai/openspec@1.11.0`, resolved on `PATH`, initialized with `--tools none` (the default installs
`/opsx:*` slash commands that duplicate the `grilling` skill). It is deliberately **not** in the gate
array: nothing in CI invokes it, so a moving version can never turn CI red. `openspec validate --strict`
is run by the author at cut time and by `mf-release` at fold time — both human-invoked.

### D10 — No `docs/sdd.md`: the method is carried by the tools, not restated in the repo

**Human decision, 2026-09-01, overriding the repo standard**, which grades `docs/sdd.md` a required file
with the contract *"the method, stated once, tool-neutral"*.

The reasoning accepted: this repo follows OpenSpec, and the method already has two homes that are
maintained by someone else. `openspec instructions <artifact>` owns artifact structure and is fetched
fresh at authoring time, so it cannot go stale. The `mf-build` / `mf-converge` / `mf-release` /
`mf-backlog-export` skills each state their own role, parameters, halting rules and findings contract, and
are loaded by the station that runs them. An in-tree `docs/sdd.md` would be a **third** statement of the
same method, maintained by hand, with nothing checking it against either — which is precisely the drift
the standard's "one subject, one home" rule exists to prevent. Applied here, that rule points *away* from
the file.

**What the repo therefore states about method, and where:** `CLAUDE.md`'s `## How a change is cut here` —
the four artifacts, the scaffold/author/validate commands, the `skip_specs` pairing, the `Change:` trailer
rule, and the recorded OpenSpec version. Nothing else.

**What is knowingly given up.** The check → converge → release half has **no in-repo statement at all**:
the findings contract, the three fail-closed rules, the `fixed`-vs-`verified` asymmetry and the release
fold live only in the skills. Two consequences a future reader should expect. A contributor without those
skills installed cannot reconstruct the loop from this repository — the repo is no longer self-describing
on that axis, which is a real weakening of the standard's one rule. And if the skills are ever revised,
this repo has no pinned statement of the contract it was built against.

*Alternative weighed:* a minimal `docs/sdd.md` carrying **only** Part II (the station line), since Part I
is what OpenSpec's instructions already own. Rejected by the human as still one restatement too many. It
remains the cheapest way to close the gap above if the trade-off is later judged wrong — roughly one page,
additive, and it would not disturb anything this change builds.

### D11 — The `docs/` tree is deferred, and `CLAUDE.md` carries the layout alone until it lands

**Human decision, 2026-09-01.** `docs/README.md` (the data flow, the seams) and `docs/modules/` (one page
per runtime module) were scoped into this change as phase 6 and removed, to be done as their own change.

**The interaction that matters:** phase 3 cuts the vault link in the same change that defers the pages
which would have replaced what the vault's implementation plan carried — the architecture, the repo layout
and the engineering conventions. Between this change and the docs change, the repo's whole architecture
record is `CLAUDE.md`'s layout and seams sections plus `README.md`'s *How it works* block. Both are short
by design; `CLAUDE.md` is explicitly capped at ~100 lines because past that it stops being read.

**Why this is acceptable but not free.** Nothing is destroyed — the vault files stay where they are, merely
unreferenced, so the deferred change can harvest them. Code-level *what* is already owned by docstrings,
which phase 1.6 improves across all 34 runtime sites. What is genuinely uncovered in the interval is the
*why* and the cross-module data flow: a reader can see each seam but not the path a prompt takes through
them. That is the gap the deferred change closes, and it is the reason it should not drift far past v0.4.

*Consequence for phase 2:* `CLAUDE.md`'s layout section must not name a `docs/` directory, since this
change no longer creates one — the standard's filling table is explicit that no directory may be listed
that does not exist. Task 2.5 verifies it.

## Risks / Trade-offs

| risk | mitigation |
|---|---|
| **Four places restate the gate array** (`minions.toml`, `Makefile`, `ci.yml`, `README.md`) and **nothing checks that they agree.** A drifted mirror documents a gate the repo does not run | They land in **one commit** (phase 1), so they are diffable side by side at review. `CLAUDE.md` adds a fifth in phase 2, carrying the "change one, change all" instruction beside it |
| Adding `D`/`ANN` touches ~34 runtime sites — a docstring can be written that is wrong, or an annotation that is wider than the truth | The 114 tests run unchanged at the phase boundary; a wrong annotation that changes behaviour cannot pass `ty check` + `pytest -q` |
| `uv sync --locked` will **fail CI** if `uv.lock` is stale relative to `pyproject.toml` — and this change edits `pyproject.toml` in three phases | Re-run `uv lock` in any phase that edits `pyproject.toml`, and commit the lock in that same phase. The failure is loud and immediate, which is why the command is first |
| Cutting the vault link **removes the only written record of the v0.2 phase workflow** from an agent's reach | `CLAUDE.md` is rewritten (phase 2) before the link is cut (phase 3); the vault files themselves are not deleted, only unreferenced, so nothing is destroyed by cutting the reference. See D11 for what stays uncovered |
| The empty `openspec/specs/` tree means the release fold is a **no-op**, so this change never exercises the machinery it installs | Accepted and named. The fold is first exercised by v0.4. `openspec validate --all --strict` still runs green over an empty tree plus a `skip_specs` change, which is the check available now |
| The human's requested phase-1 (`CLAUDE.md`) is overridden | Stated openly here and in the hand-back, with the reason. Reversible: if the human insists, `CLAUDE.md` can be written first and amended in phase 2 — at the cost of one commit that documents a nonexistent array |

## Migration Plan

Six phases, each independently committable and each ending on a green gate. There is nothing to deploy
and nothing to roll back: every artifact is additive except three prose edits (`CLAUDE.md`,
`.env.example`, one docstring), and `git revert` of any single phase leaves the repo working.

**One ordering constraint is load-bearing** (D6): the array is declared before `CLAUDE.md` quotes it.
Everything after phase 2 is order-independent.

The branch is `v0.3_mf_standards`, one branch per version, matching the repo's existing convention
(`v0.2_harden_and_identity_preserve`). Every commit carries `Change: 0003-mf-standards`.

## Open Questions

None. The four decisions that would have changed the specs, the approach or the task breakdown — the
version number, the adoption tier, the vault coupling, and the binding checker — were settled with the
human before this artifact was written, and are recorded above as D6/D8, D10, D5 and D4 respectively.
