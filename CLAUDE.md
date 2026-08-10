# synthetic_portraits — shared context for Claude Code

A self-hosted, headless pipeline: **text prompt → photoreal image of a person who does not exist** (open
SDXL models via ComfyUI on an on-demand RunPod GPU). The output feeds a downstream face-identity
anime-restyle pipeline (**"the consumer"**), which is why every image must contain one clear, frontal,
**antelopev2-detectable** face.

> **This file is shared, role-independent context — what is *true* about this repo. It is not a script.**
> What you should *do* comes from the **prompt/task you were given** (build a phase, review the branch diff,
> run a security pass, apply fixes). If your prompt conflicts with this file, **the prompt wins.** Read this
> for the facts; follow your prompt for the actions — don't infer a workflow from this file alone.

---

## The plan lives in a private vault — read it first

The full, canonical implementation plan is **not in this repo** (this repo is public — it must never
contain the vault's absolute path). The plan lives in a private Obsidian vault whose location is stored in
**`.env`** (gitignored) as **`VAULT_PROJECT_DIR`**.

1. Read `.env` and load `VAULT_PROJECT_DIR` — the absolute path to the vault project folder. If it is
   missing, copy `.env.example` → `.env` and ask the human to fill it in. **Never hardcode or print the real
   path in committed files.**
2. Read the **latest implementation plan** in `$VAULT_PROJECT_DIR/implementation_plans/` — the
   `vX.Y_implementation_plan.md` with the **highest version number**. It is the source of truth for scope,
   decisions, architecture, repo layout, the engineering conventions, the per-phase steps, **and the phase
   workflow contract**. Lower-versioned plans are completed predecessors — historical record only.
3. The plan tracks progress via its **`current_phase`** frontmatter + the **Progress ledger** (bottom of the
   plan) and the newest entries at the **top** of `$VAULT_PROJECT_DIR/log.md` — read these to see where the
   work stands. If the plan references a Phase-0 research file, read that too.

Plans and their research files live in `$VAULT_PROJECT_DIR/implementation_plans/` (version-prefixed, e.g.
`v0.2_implementation_plan.md`, `v0.2_research.md`); the project's `overview.md`, `log.md`, and `backlog.md`
sit at `$VAULT_PROJECT_DIR/`. Do not re-derive decisions already settled in the plan. If something there
conflicts with reality, raise it with the human rather than silently diverging.

---

## The quality gate (a phase is done only when all are green)

- `pytest` — all tests pass. **Test-first (red → green)** for every unit of logic.
- `ruff check` — lint clean.
- `ty` — type-check clean.
- Image-as-code phases also: `bash -n` on shell scripts + `docker build --check` clean.

The ComfyUI transport is **fully mocked** in tests (`FakeComfyClient` behind a `ComfyTransport` Protocol);
the workflow/API contract is **fixture-locked** (placeholder golden fixtures first, relocked to real node
IDs after the live GPU export). **No test hits a real GPU or the network.** CI (`ci.yml`) runs
ruff + ty + pytest on every push. Full conventions are in the plan (§ Engineering conventions).

---

## Guardrails (invariants — hold for every role)

- **Never commit `.env` or any secret** (RunPod key, the vault path, etc.). `.env` is gitignored; keep the
  vault path and all secrets there only.
- Runtime code is **stdlib-only** (the ComfyUI transport uses `urllib`), with **one sanctioned exception**:
  face detection (`insightface` + CPU `onnxruntime` / antelopev2), shipped as the optional `faces` extra and
  reached **only through the injected `FaceDetector` facade** — real at the CLI, faked in tests. Don't add
  other runtime deps unless the plan sanctions them; pytest/ruff/ty stay dev-only. (The plan's § Engineering
  conventions is authoritative.)
- **Some phases spend real money.** The plan marks metered (⚠️ GPU) phases and defines the
  stop-before-spending protocol (announce, wait for an explicit human "go", tear down, log cost). Respect it —
  never bring up a paid pod on your own initiative.
- The **vault is the single source of truth** for "where are we." If your role updates it, keep it accurate;
  a fresh session relies on it.
