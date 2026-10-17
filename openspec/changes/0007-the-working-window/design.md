# Design — 0007 the working window

How the repository moves to gpunit `v0.7.0` and renders inside a working window: the pin, the boot script, the
record kept true to the tree, the window in `gpunit.toml`, the order of commands, and one metered proof.
**Verdict: feasible** — gpunit `v0.7.0` holds the window, and its `session` takes the arguments `gpu.py` passes.

## Context

See [proposal](proposal.md) — *Why*. What holds at the cut, `main` at `419b85f` (`v0.6.0`); gpunit at `v0.7.0`
(commit `e3b819b`):

- **The pin:** `pyproject.toml:11` names `gpunit@v0.2.0`; `uv.lock:111-113` locks it, `:881` requires it. The one
  call is `gpunit.session(root / "gpunit.toml", environ=environ, cwd=root, say=say)` at
  `synthetic_portraits/gpu.py:62`; `gpu.fault_exit` (`:65-89`) handles `Lost`, `TeardownFailed`, `Refused` and
  `KeyboardInterrupt`. At `v0.7.0`, `session(spec, *, environ, cwd, say)` and those exceptions are unchanged.
- **The boot script:** `Dockerfile:90-93` `ADD`s `boot.sh` from `v0.2.0` by checksum. gpunit `v0.6.0` and later
  refuse a pod whose log lacks the session nonce: `"the image's boot.sh prints no session nonce; ADD boot.sh from
  gpunit v0.6.0"` (`gpunit/lifecycle.py:393-394` at `v0.7.0`).
- **The record:** `config/image.json` holds tag `v0.6-rc1`, its digest, and the SHA-256 of the `Dockerfile` and each
  `COPY` source; `tools/image_record.py` derives them. `.github/workflows/build-image.yml` builds on dispatch.
- **The spec:** `gpunit.toml:18` is `volume = "klklbwxdhu"`, which answers 404; the account lists no network volume.
- **The tests:** `tests/test_infra.py` — `spec_faults` (`:199-223`) wants a `volume` (`:215-216`), and its twin
  (`:232-256`) passes `"volume": "v"`; `launch_faults` (`:267-287`) holds the `ADD` tag to pyproject's, and its
  twin hard-codes `v0.2.0` (`:298`, `:305`); `test_the_build_record_agrees_with_the_tree` (`:404-414`) holds the
  record to the tree.
- **The pod side:** `pod_start.py:69-77` refuses an empty `GPUNIT_VOLUME_PATH` and uses `<volume>/models`;
  `provision.py:90-92` prints `skip (present, verified): <dest>` for a present, verified file.
- **The documents:** `CLAUDE.md:117-120` is the pod rule; README's `--pod` block is `:62-88`, and `:48` and `:56` say
  `gpunit.toml` holds "the volume".
- **gpunit's window** (README *Working window*): `volume_gb` and `volume_ceiling` together, never beside `volume`;
  `volume up` prices first and `--yes` skips the question; `.gpunit/volume` records the window; a session refuses
  with no window up, or when its ceiling plus its wait would end after the volume; `volume up` again extends; the
  window volume is named `gpunit-<project>`.

### Measurements

| what | command | result |
|---|---|---|
| `boot.sh` at `v0.7.0` | `curl -fsSL https://raw.githubusercontent.com/alxb1t/gpunit/v0.7.0/boot/boot.sh \| shasum -a 256` | `517ade6bf20d9869baeb1f1ff1ab45d9ab63c2fa477127ff11dac89611bec842` |
| the tag on the remote | `git ls-remote --tags https://github.com/alxb1t/gpunit v0.7.0` | `6ce08c6… refs/tags/v0.7.0` |
| the tag's commit | `git rev-parse 'v0.7.0^{commit}'` in a gpunit clone | `e3b819b7d0951b0a99c2cab630e97ee2fabd059a` |
| `v0.2.0` in the files that pin it | `git grep -c 'v0\.2\.0' -- pyproject.toml uv.lock Dockerfile tests/test_infra.py` | `Dockerfile:1`, `pyproject.toml:1`, `tests/test_infra.py:2`, `uv.lock:2` |
| the manifest's models | `grep -c '"dest"' config/models.json` | `10` |
| `volume_gb`'s range | `gpunit/spec.py:17` at `v0.7.0` | `VOLUME_GB = (10, 4000)` |
| a session's span | `gpunit.toml`'s `ceiling` and `timeout` | 45 min + 600 s = 55 min, inside a 4 h window |

## Goals / Non-Goals

**Goals:** `--pod` works again; the models download once a window; no volume bills between windows; every phase
ends on a green gate.

**Non-Goals:** a skill; sizes in the manifest; a new wait for the render server; choosing the data centre.

## Decisions

| id | decision | because | rejected |
|---|---|---|---|
| [D1](#d1) | gpunit pinned at `v0.7.0` and relocked; `gpu.py` unchanged (Q1) | the window is `v0.7.0`'s; the call is the same | a fork of `gpu.py` for the window |
| [D2](#d2) | `boot.sh` `ADD`ed from `v0.7.0` with its checksum; the launch twin moved to `v0.7.0` (Q1) | gpunit refuses a `boot.sh` older than `v0.6.0` | `boot.sh` from `v0.6.0` — the test holds it to pyproject's tag |
| [D3](#d3) | the record renewed in the pin's phase: `files` from the tree, `tag` `""` and a `0` × 64 digest in `config/image.json` and `gpunit.toml` until the rebuild | the `Dockerfile` edit makes the record stale; the old digest was not built from the new tree | keeping `v0.6-rc1`'s digest beside the new `files` |
| [D4](#d4) | `gpunit.toml`: `volume` → `volume_gb = 50`, `volume_ceiling = "4h"`; `spec_faults` asks for the window (Q1, Q2) | no floor and no sizes recorded; a 4 h window of 50 GB is about $0.02 | a kept volume made by hand |
| [D5](#d5) | the order of commands in `CLAUDE.md`'s pod rule and README's `--pod` section; the RunPod check covers the volume (Q3) | the repo has no skill; the rule is read before every pod | a skill — a version of its own |
| [D6](#d6) | nothing deletes the volume unasked: `volume up` again extends, `volume down` ends, the ceiling ends a forgotten window (Q4) | a working block spans batches | `volume down` inside `--pod` |
| [D7](#d7) | **HUMAN**: build `v0.7-rc1`, check the record, re-pin | only a build gives the digest | — |
| [D8](#d8) | **HUMAN · METERED**: one window, a first and a second `--pod` run on new pods, the second skipping every model (Q5) | the window, proven across pods | one run in a window |

### D1

`pyproject.toml:11` before → after: `"gpunit @ git+https://github.com/alxb1t/gpunit@v0.2.0",` →
`"gpunit @ git+https://github.com/alxb1t/gpunit@v0.7.0",`. Relock with `uv lock --upgrade-package gpunit`, so
`uv.lock` names `rev=v0.7.0#e3b819b7d0951b0a99c2cab630e97ee2fabd059a` and moves nothing else. `gpu.py`, `cli.py`
and `tests/test_cli.py` stay as they are.

### D2

`Dockerfile:91-92` before → after:

```
ADD --checksum=sha256:18742fd46a9889af6212aa76667a43a653767d53f770e0739881869a1f3b03ad \
    https://raw.githubusercontent.com/alxb1t/gpunit/v0.2.0/boot/boot.sh /opt/gpunit/boot.sh
ADD --checksum=sha256:517ade6bf20d9869baeb1f1ff1ab45d9ab63c2fa477127ff11dac89611bec842 \
    https://raw.githubusercontent.com/alxb1t/gpunit/v0.7.0/boot/boot.sh /opt/gpunit/boot.sh
```

`tests/test_infra.py:298` and `:305` say `v0.7.0` where they say `v0.2.0`; `:305`'s replacement then moves the
`Dockerfile`'s tag, so the twin still catches a boot script at another tag.

### D3

The `Dockerfile` is in the record, so its edit turns `test_the_build_record_agrees_with_the_tree` red until the
record is renewed. The edit and the pin cannot be apart: `launch_faults` holds the `ADD` tag to pyproject's.
So the pin's phase renews the record too, and the rebuild fills in the rest:

```
phase 1  Dockerfile + pin ─▶ files = image_record.py   tag ""   digest 0×64   (gpunit.toml the same) ─▶ green
phase 2  gpunit.toml window, spec_faults, documents    (no copied file moves)                      ─▶ green
phase 3  build v0.7-rc1 ─▶ its record = files?  ─▶  tag v0.7-rc1, digest written twice             ─▶ green
phase 4  the window, on the rebuilt image
```

The placeholder is `0006`'s: `config/image.json` began with `"tag": ""` and a `0` × 64 digest. It passes
`spec_faults` (a digest of 64 hex digits, equal in `gpunit.toml` and `config/image.json`), names no image a pod can pull, and leaves no record
claiming `v0.6-rc1` was built from this tree. An image with `v0.2.0`'s `boot.sh` would be refused by gpunit
`v0.7.0` anyway, after a pod had billed.

### D4

`gpunit.toml:18` before → after: `volume = "klklbwxdhu"` → `volume_gb = 50` and `volume_ceiling = "4h"`, its comment
naming this design. The first window's provisioning log gives the real total.

`spec_faults`: `if not spec.get("volume")` → a fault `"no window volume"` unless `volume_gb` is an `int`,
`volume_ceiling` is set and no `volume` is named: gpunit refuses that pairing only when `--pod` loads the spec, so
the gate faults it itself. A window over 4 hours or 50 GB is `"no window within 4 hours and 50 GB"`, the window
`CLAUDE.md`'s pod rule promises, as the session's ceiling is held to 45 minutes. The docstring, the section comment at `:196`, and the twin's `good` and `bare` dicts follow.

### D5

`CLAUDE.md`'s pod rule (`:117-120`) gains the order, and its check covers the volume:

```
uv run --env-file .env gpunit volume up --yes   ─▶  generate.py --pod … (as often as the work needs)
uv run --env-file .env gpunit volume down       ─▶  the RunPod MCP: no gpunit-synthetic-portraits pod or volume
```

It keeps 45 minutes and ~$0.30 a session, and adds the window: 4 hours, about $0.02. README's `--pod` block
(`:62-88`) opens with `volume up --yes` and ends with `volume down`; `:48` and `:56` say "the window volume's size
and ceiling" for "the volume".

### D6

No code. The documents of [D5](#d5) say it: run `volume up` again to extend a live window, `volume down` when the
work is done; the ceiling ends a window nobody closes, at the next gpunit command.

### D7

The operator pushes `v0.7_the_working_window`, dispatches `build-image.yml` on it with tag `v0.7-rc1`, checks the
summary's record equals `config/image.json`'s `files`, and writes `"tag": "v0.7-rc1"` and the digest into
`config/image.json`, and the digest into `gpunit.toml`'s `image`.

### D8

Announced, with a "go". From the repository root:

```
uv run --env-file .env gpunit volume up --yes
uv run --group faces python generate.py --pod --prompt "<README's first prompt>" --seed 42 -n 1 --out outputs/v0.7-window-1
uv run --group faces python generate.py --pod --prompt "<README's first prompt>" --seed 42 -n 1 --out outputs/v0.7-window-2
uv run --env-file .env gpunit volume down
```

Each run's output is kept as `run.log` in its `--out` directory, as `outputs/v0.6-rc1-proof/` keeps it. The first
window run's `run.log` was not kept; the second run's `provision.log` and `run.log` carry the proof. The pod's
own log is not in `generate.py`'s output: while the second session is open, the operator reads the pod's log
through the RunPod MCP's `stream-pod-logs` and saves it as `outputs/v0.7-window-2/provision.log`. It shows
`skip (present, verified)` for every entry of `config/models.json`, and no `fetching:`. Then the RunPod MCP shows
no `gpunit-synthetic-portraits` pod and no network volume. About $0.60.

## Dependencies

- `gpunit @ git+https://github.com/alxb1t/gpunit@v0.7.0` — runtime: `--pod`'s GPU session, moved from `v0.2.0`.
  Stdlib only; nothing transitive. Settled in the grilling (Q1).

## Risks / Trade-offs

- **A cold volume takes longer than 900 s** → the run refuses and its session closes; each model already landed
  stays on the window's volume, so the next `--pod` in the window goes on from there.
- **No card in stock in the window's data centre** → `volume down` and `volume up` choose a data centre afresh.
- **50 GB is too small** → the provisioning log shows the failed write; the first window's log gives the real
  total.
- **A window no command reaches after its ceiling** bills $0.07 per GB a month until one does → the pod rule's
  RunPod check names the volume.
- **The branch cannot render between the pin and the re-pin** ([D3](#d3)) → nothing meant to: phase 4 follows the
  rebuild.

## Verdict

Feasible: the window is gpunit's, the repository's part is a pin, a checksum, `volume_gb` and `volume_ceiling`, and the order of commands.
