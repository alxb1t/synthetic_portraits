---
version: v0.6
backlog: [L2-R8, R7, L2-S2]
---

# 0006 — gpunit integration

**Synthetic Portraits rents its GPU through gpunit, and no bash is left.** `generate.py --pod` opens a
`gpunit.session()`, waits for ComfyUI, renders the batch and tears down; `infra/` and `download_models.sh` leave;
the pod boots gpunit's `boot.sh` into a Python start module; the image is pinned by digest. The repository gives
gpunit a `gpunit.toml` and the key in `.env`, and names no provider in its code. **A minor: it delivers one
feature, GPU sessions through gpunit.**

| read | for |
|---|---|
| this file | why, and what changes |
| [design](design.md) | `--pod`, the seam, the pod in Python, the image's pin and record, the proof |
| [tasks](tasks.md) | the phases, in build order |
| `specs/` | `gpu-pod-provisioning` · `face-detectability` · `comfyui-execution` |

## Why

**The repository carries its own GPU lifecycle in bash**, on an older API, with the key on a command line and no
host-key check, tested by reading the scripts' text. gpunit does the lifecycle as a tested library.

**The image a pod boots is a moving tag**, and the workflow prunes all but one version on every push. A pin is
what lets a render say what it ran on.

## What Changes

- **`generate.py --pod`**: one `gpunit.session()` for the whole batch, `.env` read over the environment, the
  session's image printed, a 900 s wait for the render server ([D1](design.md#d1)–[D3](design.md#d3)).
- **`gpunit.toml`** with the pin, the cards, the floors, the 45-minute ceiling and the volume; `.env` keeps the key
  alone; `gpunit` a runtime dependency, imported lazily ([D4](design.md#d4)).
- **The pod in Python**: `synthetic_portraits/pod_start.py` and `provision.py fetch` over `config/models.json`,
  run on the image's Python 3.10; `infra/start.sh` and `download_models.sh` leave ([D5](design.md#d5),
  [D6](design.md#d6)).
- **The image under `boot.sh`**: the `ENTRYPOINT`, `curl`, no baked host key, no `PermitRootLogin` edit, telemetry
  off, `FROM` by digest ([D7](design.md#d7)).
- **The lifecycle scripts and the proxy route leave**: `infra/up.sh`, `infra/down.sh`, `RUNPOD_EXPOSE_HTTP`, and
  their tests ([D8](design.md#d8)).
- **The image built on request and recorded**: dispatch only, `latest` refused, no prune, actions by SHA,
  `config/image.json` the build record ([D9](design.md#d9)).
- **README, `CLAUDE.md`, `.env.example`** say gpunit; `CLAUDE.md` gains the ceiling ([D10](design.md#d10)).
- **A metered proof** ([D11](design.md#d11)).

## Capabilities

### New Capabilities

None.

### Modified Capabilities

- `gpu-pod-provisioning`:
  - *The pod image pins every dependency it installs* — the base by digest; the entry point gpunit's boot script.
  - *Model assets are fetched from immutable revisions and verified* — the provisioner and its manifest.
  - *The start module exposes the model volume* (added, replacing *The boot script exposes…*) — the volume alone.
  - *A batch renders on a pod through one gpunit session* (added).
  - *The image is built on request and recorded* (added, replacing *Publishing the image never deletes…*).
  - *The pod sends no usage report…* (added).
  - *Pods are created and destroyed by script…*, *Every shell script is syntax-checked…*, *Pod readiness is
    bounded…*, *Readiness polls the access path…*, *A create call that yields no pod identifier…*, *Readiness
    aborts when the container is not running* (removed) — gpunit's, or gone with the proxy.
- `face-detectability`:
  - *The face model pack is pinned and verified before it is used* — the pod's pins are the manifest's.
- `comfyui-execution`:
  - *Every request to the render server identifies its client* — the reason no longer the proxy's.

## Impact

- **Files:** `synthetic_portraits/cli.py`, `synthetic_portraits/gpu.py` (new), `synthetic_portraits/transport.py`,
  `synthetic_portraits/pod_start.py` (new), `synthetic_portraits/provision.py` (new), `config/models.json` (new),
  `config/image.json` (new), `tools/image_record.py` (new), `gpunit.toml` (new), `Dockerfile`,
  `.github/workflows/build-image.yml`, `pyproject.toml`, `uv.lock`, `.gitignore`, `.env.example`, `README.md`,
  `CLAUDE.md`, `infra/` and `download_models.sh` (deleted), and the tests.
- **Behaviour:** a render on a pod is one `--pod` command; pods are named `gpunit-synthetic-portraits`; each
  session has its own SSH key; the proxy route is gone.
- **Dependencies:** `gpunit`, at runtime ([Dependencies](design.md#dependencies)).
- **Spend:** one `--pod` batch on a real pod, under the 45-minute ceiling, by hand ([D11](design.md#d11)).

## Not in this change

- **ComfyUI's outputs in memory, PNG metadata stripped** — a synthetic subject carries no personal data.
- **A dead-container abort** — parked with gpunit, triggered by a session that waits out a dead container.
- **A change to a workflow, the prompts, the face check or the batch format.**
