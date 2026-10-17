---
version: v0.7
---

# 0007 — the working window

**Synthetic Portraits moves to gpunit `v0.7.0` and renders inside a working window.** `gpunit volume up` makes the
models volume before a `--pod` batch, and `gpunit volume down` ends it; nothing bills between windows. **A minor: it
delivers one feature, the working window.**

| read | for |
|---|---|
| this file | why, and what changes |
| [design](design.md) | the pin, the boot script, the record, the window, the order of commands, the proof |
| [tasks](tasks.md) | the phases, in build order |
| `specs/` | `gpu-pod-provisioning` |

## Why

**Pod work is broken.** `gpunit.toml`'s kept volume `klklbwxdhu` answers 404, and the account holds no network
volume, so `generate.py --pod` refuses before any create.

**A kept volume bills between batches.** gpunit `v0.7.0` makes a volume for a working window and deletes it after;
its sessions refuse a `boot.sh` older than `v0.6.0`, so the image must be rebuilt to use it.

## What Changes

- **gpunit pinned at `v0.7.0`** and relocked; the one `gpunit.session` call is unchanged ([D1](design.md#d1)).
- **`boot.sh` added from `v0.7.0`** by its checksum, and the launch check's twin moved to the new tag
  ([D2](design.md#d2)).
- **The build record follows the tree**: `config/image.json`'s `files` renewed with the `Dockerfile`, its tag and
  digest a placeholder until the rebuild ([D3](design.md#d3)).
- **`gpunit.toml` asks for a window volume**: `volume = "<id>"` → `volume_gb = 50` and `volume_ceiling = "4h"`; the
  spec check asks for the window, not an id ([D4](design.md#d4)).
- **The order of commands** in `CLAUDE.md`'s pod rule and README's `--pod` section: `volume up --yes` before a
  batch, `volume down` after, the RunPod check covering the volume ([D5](design.md#d5), [D6](design.md#d6)).
- **The image rebuilt and re-pinned**, by hand ([D7](design.md#d7)).
- **A metered proof**: one window, a first and a second `--pod` run on new pods, the second skipping every model
  ([D8](design.md#d8)).

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `gpu-pod-provisioning`:
  - *A batch renders on a pod through one gpunit session* — the session mounts the working window's volume, and its
    spec asks for a window volume, not a kept one.

## Impact

- **Files:** `pyproject.toml`, `uv.lock`, `Dockerfile`, `config/image.json`, `gpunit.toml`, `tests/test_infra.py`,
  `CLAUDE.md`, `README.md`.
- **Behaviour:** a `--pod` batch runs only inside a window that `uv run --env-file .env gpunit volume up --yes`
  opened; `.gpunit/volume` records it; the window ends at `volume down` or its 4-hour ceiling.
- **Dependencies:** `gpunit` moves `v0.2.0` → `v0.7.0` ([Dependencies](design.md#dependencies)).
- **Spend:** one window with a first and a second `--pod` run, by hand, about $0.60 ([D8](design.md#d8)).

## Not in this change

- **A skill that opens the window** — a version of its own, when the order of commands is run often enough to
  want one.
- **A change to a prompt, a model, a workflow or the manifest.** The manifest records no sizes; the first window's
  provisioning log gives the real total.
- **Deleting any volume by hand.** gpunit's `volume down` and the ceiling end a window.
- **`volume_datacenter`.** gpunit chooses the data centre from stock.
