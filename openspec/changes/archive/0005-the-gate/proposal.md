---
version: v0.5
---

# 0005 — the gate

**The `Makefile` becomes the gate's one declaration.** `.minions/minions.toml` and the test that holds its copies
equal are deleted; CI runs `make gate`; `CLAUDE.md` and `README.md` point at the `Makefile` and list no command.

Read [design](design.md) for the decisions, [tasks](tasks.md) for the phases.

## Why

The gate is declared as the `gate` array in `.minions/minions.toml`, and copied into
`Makefile`, `.github/workflows/ci.yml`, `README.md` and `CLAUDE.md`. One test, `tests/test_gate_mirrors.py`, exists
only to hold the copies equal. No station reads the array: every `mf-*` skill runs `make gate` and `make -n gate`.
One declaration needs no copy and no check.

## What Changes

- **The `Makefile` declares the gate.** Its header says so; each command carries its note as a comment above it.
- **`.minions/minions.toml` is deleted**, and `.gitignore` ignores `.minions/` whole.
- **`tests/test_gate_mirrors.py` is deleted, with no replacement.** This change authorizes the deletion
  ([D3](design.md#d3)).
- **CI runs `make gate`** as one step, in place of a step per command.
- **`CLAUDE.md` and `README.md` list no command.** They say the gate is `make gate`, and that `make -n gate` prints
  what it runs.

## Capabilities

### New Capabilities

None.

### Modified Capabilities

None. No requirement under `openspec/specs/` names the gate, so the change sets `skip_specs: true`
([D7](design.md#d7)).

## Impact

- `Makefile`, `.github/workflows/ci.yml`, `.gitignore`, `CLAUDE.md`, `README.md` — edited.
- `.minions/minions.toml`, `tests/test_gate_mirrors.py` — deleted.
- The gate's commands and their order are unchanged: `make -n gate` prints the same commands, in the same order, before and after.
- No dependency, no runtime code, no GPU.

## Not in this change

- **The spend rule** at `CLAUDE.md:118` — it is rewritten when the repo's decisions move into `docs/`.
- **The open cards in `.minions/backlog.md`** — no card's trigger fires here.
- **Pinning CI's actions to commit SHAs** — card `L2-S2` names `build-image.yml`, and its trigger has not fired.
- **The change-id rule** at `CLAUDE.md:77` — it has no slot for a patch, which is why this is a minor
  ([D6](design.md#d6)); changing the rule is its own decision.
- **Past `CHANGELOG.md` entries and archived changes** — they record what was true then.
