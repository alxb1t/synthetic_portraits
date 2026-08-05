# synthetic_portraits — operating manual for Claude Code

A self-hosted, headless pipeline: **text prompt → photoreal upper-body image of a person who does not
exist** (open SDXL models via ComfyUI on an on-demand RunPod GPU). The output feeds a downstream
face-identity anime-restyle pipeline (**"the consumer"**), which is why every image must contain one
clear, frontal, **antelopev2-detectable** face.

**You (Claude Code) write the code.** The human reviews each phase's diff, commits, and approves the
next phase.

---

## The plan lives in a private vault — read it first

The full, canonical implementation plan is **not in this repo** (this repo is public — it must never
contain the vault's absolute path). The plan lives in a private Obsidian vault whose location is stored
in **`.env`** (gitignored) as **`VAULT_PROJECT_DIR`**.

**At the start of every session:**
1. Read `.env` and load `VAULT_PROJECT_DIR` — the absolute path to the vault project folder. If it is
   missing, copy `.env.example` → `.env` and ask the human to fill it in. **Never hardcode or print the
   real path in committed files.**
2. Read `$VAULT_PROJECT_DIR/implementation_plan_v0.1.md`. It is the source of truth for scope,
   decisions, architecture, the repo layout, the engineering conventions, and the per-phase steps.
3. Find your place: the plan's `current_phase` frontmatter + the **Progress ledger** (bottom of the
   plan), then the tail of `$VAULT_PROJECT_DIR/log.md`.
4. Resume at `current_phase`. Work **one phase at a time, in order.**

The vault project folder contains:

```
$VAULT_PROJECT_DIR/
├── implementation_plan_v0.1.md   ← THE PLAN (read first, every session)
├── overview.md                   ← project state
├── log.md                        ← chronological log (append at each phase)
└── tasks.md                      ← open task checklist
```

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

When the quality gate is fully green for the current phase:

1. **Bookkeeping in the vault** (under `$VAULT_PROJECT_DIR`):
   - append a dated entry to `log.md` (`## [YYYY-MM-DD] <verb> | <title>` + what changed, test count,
     gate status);
   - check off / add items in `tasks.md`;
   - update `overview.md` (Current state, Recent activity, bump `updated`/Last activity) **and** the
     plan's `current_phase` frontmatter + the **Progress ledger** row.
2. **Provide a git commit message** (Conventional-Commits style) in chat. **Do not commit yourself** —
   the human reviews the diff and commits.
3. **Stop and wait** for the human's explicit approval before starting the next phase.

Only after approval do you begin the next phase.

---

## Metered (GPU) phases — extra care (Phases 5–6)

These spend real money — the RunPod pod bills **per second while up**. For every metered phase:

1. **Shout before spending.** Before bringing any pod up, post a clear heads-up (what it does, rough
   cost ≈ $0.34–0.69/hr, billing runs until teardown) and **wait for an explicit "go".** Do not create
   the pod until then.
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
- Runtime code stays **zero third-party dependency** (stdlib only); pytest/ruff/ty are dev-only.
- Don't skip the test-first step or the vault bookkeeping. The vault is the single source of truth for
  "where are we" — a fresh session relies on it.
