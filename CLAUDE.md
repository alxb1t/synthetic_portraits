# synthetic_portraits — operating manual for Claude Code

A self-hosted, headless pipeline: **text prompt → photoreal upper-body image of a person who does not
exist** (open SDXL models via ComfyUI on an on-demand RunPod GPU). The output feeds a downstream
face-identity anime-restyle pipeline (**"the consumer"**), which is why every image must contain one
clear, frontal, **antelopev2-detectable** face.

**You (Claude Code) write the code**, test-first. For local ($0) phases you commit each green phase and
continue autonomously; you pause for the human only before a **metered (GPU) phase** or on genuine
ambiguity. The active plan's phase workflow contract is authoritative (see below).

---

## The plan lives in a private vault — read it first

The full, canonical implementation plan is **not in this repo** (this repo is public — it must never
contain the vault's absolute path). The plan lives in a private Obsidian vault whose location is stored
in **`.env`** (gitignored) as **`VAULT_PROJECT_DIR`**.

**At the start of every session:**
1. Read `.env` and load `VAULT_PROJECT_DIR` — the absolute path to the vault project folder. If it is
   missing, copy `.env.example` → `.env` and ask the human to fill it in. **Never hardcode or print the
   real path in committed files.**
2. Read the **latest implementation plan** in `$VAULT_PROJECT_DIR/implementation_plans/` — the
   `vX.Y_implementation_plan.md` file with the **highest version number**. It is the source of truth for
   scope, decisions, architecture, the repo layout, the engineering conventions, the per-phase steps,
   **and the phase workflow contract (how and when you commit, and when you pause).** Lower-versioned
   `vX.Y_implementation_plan.md` files are completed predecessors — historical record only; don't
   execute them.
3. Find your place: the plan's `current_phase` frontmatter + the **Progress ledger** (bottom of the
   plan), then the latest entries at the **top** of `$VAULT_PROJECT_DIR/log.md`, then (if the plan
   references it) its Phase-0 research file.
4. Resume at `current_phase`. Work **one phase at a time, in order.**

Plans and their research files live in `$VAULT_PROJECT_DIR/implementation_plans/` (version-prefixed, e.g.
`v0.2_implementation_plan.md`, `v0.2_research.md`); the project's `overview.md`, `log.md`, and `backlog.md`
sit at `$VAULT_PROJECT_DIR/`. Browse the folder yourself; if anything is unclear, ask the human rather
than guessing.

Do not re-derive decisions already settled in the plan. If something there conflicts with reality,
raise it with the human rather than silently diverging.

---

## The quality gate (a phase is done only when all are green)

- `pytest` — all tests pass. **Test-first (red → green)** for every unit of logic.
- `ruff check` — lint clean.
- `ty` — type-check clean.
- Image-as-code phases also: `bash -n` on shell scripts + `docker build --check` clean.

The ComfyUI transport is **fully mocked** in tests (`FakeComfyClient` behind a `ComfyTransport`
Protocol); the workflow/API contract is **fixture-locked** (placeholder golden fixtures first, relocked
to real node IDs after the live GPU export). **No test hits a real GPU.** CI (`ci.yml`) runs
ruff + ty + pytest on every push. Full conventions are in the plan (§ Engineering conventions).

---

## The per-phase loop (do this at the end of every phase)

**The active plan's § "phase workflow contract & metered protocol" is authoritative — follow it.** In
brief, when the quality gate is fully green for the current phase:

1. **Bookkeeping in the vault** (under `$VAULT_PROJECT_DIR`):
   - **prepend** a dated entry at the **top** of `log.md` (`## [YYYY-MM-DD] <verb> | <title>` + what
     changed, test count, gate status) — newest first;
   - record any deferred / next-version work in `backlog.md`;
   - update `overview.md` **Current state** (bump `updated`/Last activity) **and** the plan's
     `current_phase` frontmatter + the **Progress ledger** row.
2. **Commit** the phase with a Conventional-Commits message (in this code repo; the vault bookkeeping is
   not part of this commit).
3. **Continue autonomously into the next phase** when it is local ($0). **Stop and wait for the human**
   only before a **metered (GPU) phase** or on **genuine ambiguity/doubt** — then ask one focused
   question and resume after the answer. See the plan for the exact stop conditions.

---

## Metered (GPU) phases — extra care

The plan marks which phases are metered (⚠️). These spend real money — the RunPod pod bills **per second
while up**. For every metered phase:

1. **Shout before spending.** Before bringing any pod up, post a clear heads-up (what it does, rough cost
   — the Blackwell tier used ≈ $0.72/hr; see the plan's cost estimate — billing runs until teardown) and
   **wait for an explicit "go".** Do not create the pod until then.
2. **Pre-flight at $0** — the whole local gate must be green before the pod comes up.
3. **Keep the human posted on pod state** (up / downloading / rendering / torn down).
4. **Hand off for visual verification** — when output needs human judgment (photoreal? face detectable?
   pose/clothes right?), `scp` the render(s) off the pod and **ask the human to confirm it works before
   the step is done or anything is torn down.**
5. **Tear down promptly** after verification; record actual GPU time + cost in `log.md`.

---

## Guardrails

- **Never commit `.env` or any secret** (RunPod key, the vault path, etc.). `.env` is gitignored; keep
  the vault path and all secrets there only.
- Runtime code is **stdlib-only** (the ComfyUI transport uses `urllib`), with **one sanctioned
  exception**: face detection (`insightface` + CPU `onnxruntime` / antelopev2), shipped as the optional
  `faces` extra and reached **only through the injected `FaceDetector` facade** — real at the CLI, faked
  in tests. Don't add other runtime deps without the plan sanctioning them. pytest/ruff/ty stay dev-only.
  (The active plan's § Engineering conventions is authoritative on this.)
- Don't skip the test-first step or the vault bookkeeping. The vault is the single source of truth for
  "where are we" — a fresh session relies on it.
