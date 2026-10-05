# Design — 0005 the gate

**How the gate's copies become one declaration in the `Makefile`.** Verdict: `feasible` — config, CI and
prose; no command or order changes.

## Context

See [proposal](proposal.md) — Why. Measured on `main` at `8185c80` (`v0.4.0`):

| fact | measured by |
|---|---|
| the array holds `uv sync --locked`, `uv run ruff format --check .`, `uv run ruff check .`, `uv run ty check`, `uv run pytest -q`, in that order | `cat .minions/minions.toml`; `make -n gate` prints the same lines |
| the copies sit at `Makefile:1-15`, `.github/workflows/ci.yml:3-5` and `:21-35`, `README.md:129-145`, `CLAUDE.md:18-34` | reading each file |
| the array is also named at `CLAUDE.md:88-91` (openspec tooling) and `:103` (layout), and `.gitignore:10-13` | `grep -n 'array\|minions.toml' CLAUDE.md .gitignore` |
| no station reads the toml: `mf-cut-change`, `mf-build`, `mf-converge` and `mf-release` run `make gate` and `make -n gate` | `grep -n 'minions.toml\|make -n gate' ~/.claude/skills/mf-*/SKILL.md` |
| no requirement names the gate | `grep -rn -i 'minions.toml\|gate array' openspec/specs` prints nothing |
| only `tests/test_gate_mirrors.py` reads the toml; it is `STRUCTURAL_GUARD`, bound to no scenario | `grep -rn 'minions.toml' tests/` |

```
before                                   after
.minions/minions.toml  ◀── the truth     Makefile  ◀── the truth, with a note per command
  ├─ Makefile          ┐                   ├─ ci.yml      runs `make gate`
  ├─ ci.yml            │ copies,           ├─ README.md   says `make gate`, `make -n gate`
  ├─ README.md         │ held equal by     └─ CLAUDE.md   says `make gate`, `make -n gate`
  └─ CLAUDE.md         ┘ test_gate_mirrors
```

## Goals / Non-Goals

**Goals:** one declaration; no copy of a command anywhere else; `make -n gate` prints what it printed before.

**Non-Goals:** changing a gate command or its order; anything in [proposal](proposal.md) — Not in this change.

## Decisions

| id | decision | because | rejected |
|---|---|---|---|
| [D1](#d1) | the `Makefile` is the one declaration; `minions.toml` is deleted; each command's note becomes a comment | no station reads the toml | keeping the toml as the truth |
| [D2](#d2) | CI is one step: `run: make gate` | a step per command is a copy | keeping a step per command |
| [D3](#d3) | `tests/test_gate_mirrors.py` is deleted, with no replacement | with one declaration nothing is left to hold equal | a guard that no file lists a command |
| [D4](#d4) | `CLAUDE.md` and `README.md` list no command; the "array" passages name the `Makefile` | a list in prose is a copy | a list kept "for reading" |
| [D5](#d5) | `.gitignore` ignores `.minions/` whole | nothing in it is tracked any more | keeping the `!` exception |
| [D6](#d6) | `v0.5`, a minor, `0005-the-gate` | the id rule at `CLAUDE.md:77` has no slot for a patch | `v0.4.1` with a new id rule |
| [D7](#d7) | `skip_specs: true` and `specs/.gitkeep` | no requirement names the gate | a requirement written to have a delta |
| [D8](#d8) | phases: declare once, then prose | the toml and its test go in one commit, or the gate is red | one phase |

### D1

**The `Makefile` declares the gate.** `.minions/minions.toml` is deleted.

- `Makefile:1-6`, before: *"These recipe lines mirror the `gate` array in `.minions/minions.toml` byte for byte …
  tests/test_gate_mirrors.py fails if any of them drifts from it."* After: *"The gate: this recipe is its one
  declaration. CI and the MinionsFactory skills run `make gate`; `make -n gate` prints what it runs."*
- **Each command's note moves from `CLAUDE.md:22-26`** to a comment directly above that command:

  ```make
  gate:
  # the environment: certifies what uv.lock pins, not whatever .venv holds
  	uv sync --locked
  # format, in check mode (a formatter in rewrite mode is not the check)
  	uv run ruff format --check .
  # lint: E,F,I,UP,B,SIM,D,ANN; tests/** exempt from D1, D401 and ANN
  	uv run ruff check .
  # strict types
  	uv run ty check
  # the suite, offline and deterministic
  	uv run pytest -q
  ```

- **A comment sits at column 0**, never after a tab: a tab-led `#` line is a recipe line, and `make -n gate` would
  print it.
- **The `docker build --check` and `bash -n` reasons** stay in `CLAUDE.md:31-34`, per [D4](#d4).

### D2

**CI runs the `Makefile`.** `.github/workflows/ci.yml:21-35`, the step per command, becomes one step:

```yaml
      # The gate is the Makefile's `gate` target. CI runs it rather than keeping
      # its own copy of the commands, which would drift.
      - name: Gate
        run: make gate
```

`ci.yml:3-5`'s header, which calls the file "one of its four mirrors", is deleted. The checkout and `setup-uv`
steps are unchanged. `ubuntu-latest` carries `make`.

### D3

**`tests/test_gate_mirrors.py` is deleted, with no replacement.** `CLAUDE.md` says a deleted test is a plan
problem, never a coding shortcut; **this decision is the plan that authorizes it.** The test reads the toml, which
[D1](#d1) deletes, and holds the copies equal, which [D2](#d2) and [D4](#d4) remove. It is a `STRUCTURAL_GUARD`,
bound to no scenario, so no spec key loses its test.

### D4

**The prose points at the `Makefile`.**

| place | before | after |
|---|---|---|
| `CLAUDE.md:18` | *"## The quality gate — this repo's 5 commands"* | *"## The quality gate"* |
| `CLAUDE.md:20-29` | the list, and *"`Makefile`'s `gate` target, `README.md` and CI mirror that array …"* | *"**The gate is `make gate`**, run from the repository root; `make -n gate` prints what it runs. The `Makefile` declares it and notes each command; CI runs `make gate` too."* |
| `CLAUDE.md:31-34` | *"`docker build --check` is deliberately *not* in the array … the array must run on any checkout"* | the same reasons, naming the gate in place of the array |
| `CLAUDE.md:88-91` | *"deliberately **not** in the gate array … The binding authority for the code is the array, whose last entry is `pytest -q`"* | *"not in the gate … The binding authority for the code is the gate, whose last command is `pytest -q`"* |
| `CLAUDE.md:103` | *"`.minions/` — run artefacts, **gitignored**; `minions.toml`, the gate array, is the one tracked file."* | *"`.minions/` — MinionsFactory's run artefacts, gitignored whole."* |
| `README.md:129-145` | *"It runs the five commands declared in `.minions/minions.toml`'s `gate` array"*, the list, *"That array is the single source of truth …"* | *"`make -n gate` prints its commands; the root `Makefile` declares them, and CI runs `make gate` too."* The coverage sentence and the `docker build --check` sentence stay, naming the gate in place of the array |

The fenced `make gate` block at `README.md:125-127` stays.

### D5

**`.gitignore:10-13`**, before: *"# Run artefacts … The declared gate array is the one tracked file in here."*,
`.minions/*`, `!.minions/minions.toml`. After:

```
# MinionsFactory's run artefacts: findings, frozen diffs, the backlog. All local.
.minions/
```

### D6

**A minor: `v0.5`, change `0005-the-gate`, branch `v0.5_the_gate`, tag `v0.5.0`.** No product behaviour changes,
so in spirit it is a patch. But `CLAUDE.md:77` derives the id as `(major × 100) + minor`, and a patch `v0.4.1`
would take `0004`, the id of the change that shipped `v0.4.0`. Changing that rule is out of scope.

### D7

**No spec delta.** `.openspec.yaml` sets `skip_specs: true`, and `specs/.gitkeep` holds the directory. No
requirement under `openspec/specs/` names the gate, the array or the toml.

### D8

**Phases**, each green alone:

```
1 declare once   D1 · D2 · D3 · D5    Makefile, ci.yml, .gitignore; toml and test deleted
2 prose          D4                   CLAUDE.md, README.md
```

Phase 1 deletes the toml and its test in one commit: either alone turns the gate red.

## Dependencies

None.

## Risks / Trade-offs

- **A comment in the recipe is printed or run.** → [D1](#d1) puts every comment at column 0; task 1.1 checks
  `make -n gate` prints exactly the gate's commands.
- **CI's log loses its per-command step names.** → `make` echoes each command before it runs and stops at the
  first that fails, so the failing command is the last line printed.
- **A copy survives in prose.** → task 2.3 greps the tree for `minions.toml` and `gate_mirrors`.

## Verdict

**`feasible`.** Every site re-checked at `8185c80`; the gate's commands and order are unchanged.
