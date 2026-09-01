# synthetic_portraits — shared context for Claude Code

A self-hosted, headless pipeline: **text prompt → photoreal image of a person who does not exist** (open
SDXL models via ComfyUI on an on-demand RunPod GPU). Its output feeds a downstream face-identity
anime-restyle pipeline (**"the consumer"**), which is why every image must contain one clear, frontal,
**antelopev2-detectable** face.

Two commitments shape all the code here and must not be violated without a recorded decision: the runtime
package is **stdlib-only**, and **no test reaches a GPU or the network**.

> **This file is shared, role-independent context — what is *true* about this repo. It is not a script.**
> What you should *do* comes from the **prompt/task you were given**. If your prompt conflicts with this
> file, **the prompt wins.** Read this for the facts; follow your prompt for the actions — don't infer a
> workflow from this file alone.

---

## The quality gate — this repo's 5 commands

**These** are the commands this repo declares, in `.minions/minions.toml`'s `gate` array, in order:

- `uv sync --locked` — the environment; certifies what `uv.lock` pins, not whatever `.venv` holds
- `uv run ruff format --check .` — format, in check mode (a formatter in *rewrite* mode is not it)
- `uv run ruff check .` — lint (`E,F,I,UP,B,SIM,D,ANN`; `tests/**` exempt from `D1`/`D401`/`ANN`)
- `uv run ty check` — strict types
- `uv run pytest -q` — the suite, offline and deterministic

`Makefile`'s `gate` target, `README.md` and CI mirror that array, and `tests/test_gate_mirrors.py` fails
if any of them drifts from it. `make gate` is the one command a human types.

**`docker build --check` is deliberately *not* in the array** — it needs a running Docker daemon, and the
array must run on any checkout, offline. `build-image.yml` does a real image build on every push to
`main`, which subsumes it; run it by hand for image-as-code work. `bash -n` needs no entry either:
`tests/test_infra.py` already runs it over every shell script, so `pytest -q` carries that axis.

**External effects are faked at four seams**, which is what keeps the suite offline:

- **`ComfyTransport`** (`transport.py`) — a Protocol. `ComfyClient` is real (stdlib `urllib`);
  `FakeComfyClient` replays `/prompt` → `/history` → `/view` in memory, including both error paths.
- **`FaceDetector`** (`faces.py`) — a facade. `ScriptedFaceDetector` returns a scripted per-attempt
  count, so the regenerate loop is testable.
- **`workflows/*.json`** — golden fixtures, locked to real node ids exported from a live GPU run.
- **`await_outputs(..., sleep=)`** — the poll clock is injected, so timeout paths cost no wall time.

---

## Engineering conventions

The active change's **`design.md`** is authoritative, with this file behind it — read it. It *is* the
decision record: the reasoning and the measurement behind each decision live there and nowhere else.

- **Runtime is stdlib-only**, with **one sanctioned exception**: face detection (`insightface` + CPU
  `onnxruntime` / antelopev2), shipped as the optional `faces` extra and reached **only** through the
  injected `FaceDetector` facade — real at the CLI, faked in tests. `pytest`/`ruff`/`ty` stay dev-only.
- **Test-first (red → green)** for every unit of logic this project owns. Tests are named as behavioural
  sentences and double as documentation — which is why `tests/**` is exempt from the docstring selectors.
- **Conventional Commits, one phase = one commit**, staged **by name** — never `git add -A`, because
  `.minions/` holds gitignored run output.

---

## How a change is cut here

Work is defined before it is built, as a change under `openspec/changes/<id>/`. A change is **four
artifacts, always all four**: `proposal.md` · `specs/` · `design.md` · `tasks.md`.

1. **Settle the decisions first**, argued against a person, not from a first draft.
2. **Scaffold** — `openspec new change <NNNN-slug>`.
3. **Author** each artifact against `openspec instructions <artifact> --change <NNNN-slug>`, one at a time,
   fetching each immediately before writing it. `proposal.md` additionally opens with `version: vX.Y`
   frontmatter — **the CLI neither emits nor checks it; it is on the author.**
4. **A change that changes no requirement** declares the absence rather than inventing one: `skip_specs:
   true` in the change's tracked `.openspec.yaml`, plus `specs/.gitkeep`. The two are mutually exclusive.
   Never write a requirement solely to satisfy the validator.
5. **Finish on a green check** — `openspec validate <NNNN-slug> --strict`.

Change id is `<digits>-<lowercase-slug>`; version → id is `(major × 100) + minor`, zero-padded. Progress
lives in `tasks.md`'s `## Progress` plus git: a phase is done by a commit **and** a ticked box.

Every commit carries a `Change: <change-id>` git trailer, in the trailer block at the end of the message
and **contiguous** with any `Co-Authored-By:` line — a blank line between them silently breaks the block.

**The rest of the method is carried by the tools, not restated here.** `openspec instructions <artifact>`
owns artifact structure, fetched fresh at authoring time; the `mf-build`, `mf-converge`, `mf-release` and
`mf-backlog-export` skills own the build, check, converge and release stations, each stating its own role,
halting rules and findings contract. This repo keeps no `docs/sdd.md` — a third copy would only drift.

The tooling is **operator tooling, recorded and not pinned**: `@fission-ai/openspec@1.11.0` on `PATH`,
initialized with `--tools none`. It is deliberately **not** in the gate array — nothing in CI runs it, so a
moving version can never turn CI red. The binding authority for the code is the array, whose last entry is
`pytest -q`; there is no spec↔test binding check yet (no spec tree binds).

---

## Layout — where things live here

- **`synthetic_portraits/`** — the runtime package: `transport` (the ComfyUI seam), `workflow` (trace-based
  prompt injection), `models` (name→model registry), `pipeline` (render + face gate + regenerate loop),
  `faces`, `batch`, `cli`. **`generate.py`** is the entry point. **`tests/`** — the suite.
- **`infra/`** — pod up/down/boot scripts. **`workflows/`** — the ComfyUI API-format graphs.
  **`scripts/`** — `check_face.py`, the offline detectability assertion. **`examples/`** — the demo set.
- **`openspec/`** — the living specs and the changes. **`.github/`** — CI and the image build.
- **`.minions/`** — run artefacts, **gitignored**; `minions.toml`, the gate array, is the one tracked file.
- **Everything a run reads or writes is inside the repository.** No path outside the repo is resolved.

---

## Guardrails (invariants — hold for every role)

- **Never commit a secret, or a *real* absolute path from the machine the run is on** — an API key, the
  operator's home, or this repository's own root. `.env` is gitignored; `.env.example` is path-free.
- **Deps minimal + human-gated.** Any new dependency — argue for it and **wait for approval** before
  installing. Test/lint/type tools stay dev-only; keep the runtime lean.
- **Never weaken the gate to pass.** A deleted or skipped test, a blanket suppression, a loosened config —
  each is a *plan* problem, not a coding shortcut. **Halt and say so.**
- **State lives on disk.** Reconstruct "where are we" from `tasks.md` + git, never from memory.
- **Some work spends real money.** Pods bill per second. Announce, wait for an explicit human "go", tear
  down afterwards, and never bring up a paid pod on your own initiative.
- **Every image is of a person who does not exist**, is disclosed as AI-generated, and the pipeline is
  never pointed at a real individual's likeness.
