## Context

See `proposal.md` — Why. The constraints that shape the approach, all measured on 2026-09-01 against
`HEAD = d297ddb`:

| measured | value |
|---|---|
| tests, all offline and passing | **120 collected** across 10 files (114 `def test_` plus parametrization) |
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

### D3 — This change declares `skip_specs: true` — reversed 2026-09-01, restored 2026-09-02

**As built, this decision holds**, though not for the reason it was first written and not with the
consequence it first had. The change is **zero-delta**: `skip_specs: true` is in `.openspec.yaml`,
`specs/.gitkeep` is present, and the change's own `specs/` directory is empty. What changed between
the two dates is *where the backfill lives*, not whether it happens — see D14.

**The original reasoning, which still stands.** Adopting a method changes no behaviour, and the
standard is explicit: **never invent a requirement to satisfy the validator.** The combination that
passes is `skip_specs: true` plus `specs/.gitkeep` — a non-`.md` file, so the directory stays tracked
and no spec file exists. A `specs/README.md` saying "no delta" fails; so does omitting `skip_specs`.

**What no longer stands: the deferral.** The original text went on to reject backfilling the pipeline's
capability specs in this change, on size — 120 tests across 7 runtime modules being a change of its
own — and named it a non-goal deferred to v0.4. D12 overrode that on 2026-09-01 and pulled the
backfill in as phase 7. **The backfill happened.** It simply landed in `openspec/specs/` directly
rather than as a delta under this change, which is why `skip_specs` is correct again: a change that
*documents* existing behaviour proposes no requirement change, so it has no delta to declare.

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

**Updated by D12 (2026-09-01).** There now *is* a tree — phase 7 backfills 100 scenarios and binds
every one of them to a proving test with a `spec` marker, and the structural guards carry
`spec_exempt`. The condition this decision named as its trigger is therefore met, and the decision
still stands: the binding exists but nothing enforces it, and the gate array gains no entry. Writing
the checker is its own decision, for its own change.

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

### D12 — The specs are backfilled in this change after all, as phase 7

**Human decision, 2026-09-01, reversing D3.** The living specs are written now rather than at v0.4.

**What the reversal costs, stated plainly.** D3's size argument was not refuted, it was overridden: the
behaviour to describe is unchanged at 132 tests across seven runtime modules, and phase 7 is therefore the
largest phase in the change by some margin. The standard's own guidance is to split a bundle rather than
grow one, so 7.1 exists partly to *measure* the backfill — if the capability count makes a single phase
unreviewable, splitting it into its own change remains the right move and 7.1 is where that becomes visible.

**What it buys.** Without it, `openspec/specs/` ships empty, so the standard is adopted with nothing in
the tree it exists to fill — the gap named in the risk table below. Phase 7 closes it: v0.3 ships a living
spec tree describing what the pipeline actually does, and the next change is cut against a tree that
already says something.

**What it does not change.** The binding **checker** stays deferred (D4). Phase 7.5 binds each scenario to
a proving test with a marker and verifies that binding by command, but adds no gate entry — the standard
grades the checker advisory, and writing one is a separate decision from having a spec tree for it to read.

**Amended 2026-09-02 by D14.** This decision was first built as a *delta* under the change, on the
reasoning that doing so would also exercise the release fold. The human corrected the placement: a
backfill describes current functionality, not a change to it, so it belongs in `openspec/specs/`
directly. The backfill stands; only its location moved, and with it the claim about exercising the
fold, which D14 retires.

### D13 — The capability map: seven capabilities, enumerated from behaviour and bound to tests

**The measurement, run 2026-09-01.** `uv run pytest --collect-only` reports **132 tests across 13
files**. Of those, **41** are structural guards of the repository itself — `test_gate_mirrors.py`
(5), `test_repo_hygiene.py` (4), `test_version_line.py` (3) and `test_infra.py`'s shell-script and
file-set checks — and the remaining **91** exercise the product. The seven capabilities below were
enumerated from those tests and from the CLI surface (`--prompt` / `--prompts`, `--identity`,
`--model`, `--negative`, `--width` / `--height`, `--seed`, `--count`, `--out`, `--server`), **not**
from `synthetic_portraits/*.py` — which is why `workflow.py` does not appear as a capability (its
graph tracing is a guarantee *of* `portrait-generation` and `identity-preserving-generation`) and why
`models.py` does (choosing a model is a decision the caller makes).

| capability | reqs / scenarios | proved by |
|---|---|---|
| `portrait-generation` | 7 / 23 | `test_cli.py`, `test_workflow.py`, `test_pipeline.py` |
| `face-detectability` | 5 / 18 | `test_pipeline.py`, `test_cli.py`, `test_faces.py`, `test_check_face.py` |
| `identity-preserving-generation` | 3 / 13 | `test_identity.py`, `test_cli.py`, `test_workflow.py`, `test_pipeline.py` |
| `batch-generation` | 3 / 11 | `test_batch.py`, `test_cli.py` |
| `model-selection` | 2 / 5 | `test_models.py`, `test_cli.py` |
| `comfyui-execution` | 4 / 11 | `test_transport.py` |
| `gpu-pod-provisioning` | 5 / 19 | `test_infra.py` |
| **total** | **29 / 100** | |

**Every scenario carries a `Key:` and the `Layers:` it is proved at.** Three layer names are used,
and they are honest about strength rather than uniform: `unit` (a function called directly), `cli`
(end to end through `main`, against the fake transport and a scripted detector), and `structural`
(asserted by reading a tracked file — a golden workflow fixture, the `Dockerfile`, a shell script).
A `structural` scenario proves the artefact *says* the right thing, not that it *did* the right thing
on a pod; it is labelled so a reader can see which claims rest on that.

**Verified by command, not by eye.** Extracting every `Key:` from `openspec/specs/` and every
`pytest.mark.spec(...)` argument from `tests/`, sorting both and diffing them, yields no difference:
100 keys, 100 bound, none orphaned in either direction.

**Gaps — behaviour the code has and the suite does not prove.** Recorded here rather than specified,
because a scenario no test backs is a requirement this repo has not earned:

- **The server address is configurable** (`--server`, defaulting to `COMFY_URL` and then to
  localhost). No test constructs the real client from the flag; every test injects a transport, which
  is exactly what keeps the suite offline. Closing it means asserting the URL a `ComfyClient` is
  built with.
- **The output directory defaults to `outputs/`.** Every test passes `--out` at a `tmp_path`, so the
  default string is unproven. `portrait.saves-render` covers writing to the *requested* directory
  only.
- **`--negative` overrides the default negative prompt.** The default's content and its injection are
  both proved; the CLI flag's override path is not.
- **The image is photoreal, and of a person who does not exist.** Not provable offline at any layer
  this suite can reach — it is a property of a GPU render, and the repo's evidence for it is the
  `examples/` set plus `scripts/check_face.py`.

*Alternative weighed:* write the four missing scenarios and mark them pending. Rejected — a pending
scenario is a requirement the tree claims and the gate does not hold, which is the failure mode
`spec_exempt` and this table exist to avoid. They belong in whichever change adds the tests, and
because the tree is now live (D14), that change will carry them as a real `ADDED` delta.

*Alternative weighed:* leave `gpu-pod-provisioning` out, on the grounds that all 19 of its scenarios
are `structural`. Rejected — the guarantees are real and externally consequential (a pinned revision,
a verified digest, a pod that stops billing), and dropping them would leave the repo's most
security-relevant behaviour undescribed. The `Layers:` label carries the caveat instead.

*Splitting was reconsidered here, as D12 asked.* Seven capabilities and 29 requirements is large for
one phase but not unreviewable, and the phase adds no behaviour — the diff is prose plus 100
one-line markers, reviewable capability by capability. It stays one phase.

### D14 — The backfill is seeded directly into `openspec/specs/`, not cut as a delta

**Human decision, 2026-09-02**, correcting how D12's backfill was first built. Phase 7 originally wrote
the seven capabilities as `## ADDED Requirements` under `openspec/changes/0003-mf-standards/specs/`,
leaving the change delta-bearing. They now live in `openspec/specs/<capability>/spec.md` as
`## Requirements`, and the change is zero-delta again (D3).

**Why the delta form was wrong.** A delta is a statement of what a change *changes*. Every one of these
100 scenarios describes behaviour that shipped in v0.1 or v0.2 and that this change does not touch — so
`ADDED` was false on its face: nothing was being added by change 0003. Worse, it would have been folded
into the living tree at release under a heading claiming v0.3 introduced `portrait-generation`, which is
the sort of drift the whole standard exists to prevent. The living tree is *the description of current
functionality*; a backfill belongs there directly.

**Why `skip_specs: true` is then correct, not a dodge.** The marker declares that the change proposes no
spec-level behaviour change. That is precisely true: the pipeline behaves identically before and after,
and no requirement is added, modified or removed by it. Creating `openspec/specs/` is adoption work, the
same as creating `CHANGELOG.md` in phase 5 — it documents what is, it does not change it.

**What this costs, stated plainly.** D12 claimed the backfill would exercise the release fold on this
change's own release. **It no longer does.** `mf-release` will fold an empty delta, so the fold, the
`MODIFIED`-replaces-by-title behaviour and the archive ordering are all still untried, and will first
run on whichever change actually changes a requirement — v0.4. That is a genuine loss of one
rehearsal, accepted knowingly. The counter-argument the human's correction rests on is that the
rehearsal was never worth buying with a false delta, and that a fold first exercised on a real
requirement change is a more honest test of it than one exercised on a fabricated one.

*Alternative weighed:* keep the delta **and** hand-write the living tree, so both are populated.
Rejected — the same 100 scenarios in two places with nothing checking they agree, and `openspec archive`
would then fold requirements that are already present. The duplication is exactly the drift the
"one subject, one home" rule forbids.

*Alternative weighed:* run `openspec archive 0003-mf-standards` now, letting the tool do the fold.
Rejected — archive also moves the change into `changes/archive/`, which is the release station's job on
a converged change. This one is not converged, and phase 7 is not a release.

**Verification is unchanged in substance, only in path.** The binding check now extracts every `Key:`
from `openspec/specs/` rather than from the change delta; it still reports 100 keys, 100 bound, none
orphaned in either direction. `openspec validate --all --strict` now validates eight items — the change
plus the seven living specs — where before it validated one.

## Risks / Trade-offs

| risk | mitigation |
|---|---|
| **Four places restate the gate array** (`minions.toml`, `Makefile`, `ci.yml`, `README.md`) and **nothing checks that they agree.** A drifted mirror documents a gate the repo does not run | They land in **one commit** (phase 1), so they are diffable side by side at review. `CLAUDE.md` adds a fifth in phase 2, carrying the "change one, change all" instruction beside it |
| Adding `D`/`ANN` touches ~34 runtime sites — a docstring can be written that is wrong, or an annotation that is wider than the truth | The 120 tests run unchanged at the phase boundary; a wrong annotation that changes behaviour cannot pass `ty check` + `pytest -q` |
| `uv sync --locked` will **fail CI** if `uv.lock` is stale relative to `pyproject.toml` — and this change edits `pyproject.toml` in three phases | Re-run `uv lock` in any phase that edits `pyproject.toml`, and commit the lock in that same phase. The failure is loud and immediate, which is why the command is first |
| Cutting the vault link **removes the only written record of the v0.2 phase workflow** from an agent's reach | `CLAUDE.md` is rewritten (phase 2) before the link is cut (phase 3); the vault files themselves are not deleted, only unreferenced, so nothing is destroyed by cutting the reference. See D11 for what stays uncovered |
| The release fold this change installs is a no-op on this change's own release, so the fold, `MODIFIED`-replaces-by-title and the archive ordering all go untried until v0.4 | **Accepted, not closed** (D14). D12 backfills the specs so `openspec/specs/` ships populated rather than empty — the tree is no longer the gap. The fold is exercised by the first change that actually changes a requirement, which is a more honest test of it than a fabricated delta would have been |
| The human's requested phase-1 (`CLAUDE.md`) is overridden | Stated openly here and in the hand-back, with the reason. Reversible: if the human insists, `CLAUDE.md` can be written first and amended in phase 2 — at the cost of one commit that documents a nonexistent array |

## Migration Plan

Seven phases — six as cut, plus the spec backfill D12 added — each independently committable and each
ending on a green gate. There is nothing to deploy and nothing to roll back: every artifact is additive
except three prose edits (`CLAUDE.md`, `.env.example`, one docstring), and `git revert` of any single
phase leaves the repo working.

**One ordering constraint is load-bearing** (D6): the array is declared before `CLAUDE.md` quotes it.
Everything after phase 2 is order-independent. Phase 7 writes into `openspec/specs/` and leaves this
change zero-delta (D14), so it imposes no ordering constraint of its own.

The branch is `v0.3_mf_standards`, one branch per version, matching the repo's existing convention
(`v0.2_harden_and_identity_preserve`). Every commit carries `Change: 0003-mf-standards`.

## Open Questions

None. The four decisions that would have changed the specs, the approach or the task breakdown — the
version number, the adoption tier, the vault coupling, and the binding checker — were settled with the
human before this artifact was written, and are recorded above as D6/D8, D10, D5 and D4 respectively.
