# Design — 0006 gpunit integration

How the repository moves its GPU onto gpunit: one flag over one session, one seam, the pod's two scripts in
Python, the image pinned and recorded, and one metered proof. **Verdict: feasible** — gpunit `v0.2.0` holds the
lifecycle, and isekai `v0.35` and `v0.35.1` already took this path.

## Context

See [proposal](proposal.md) — *Why*. What holds at the cut, `main` at `2bd0b72` (`v0.5.0`); gpunit at `v0.2.0`:

- **The CLI:** `build_parser` (`synthetic_portraits/cli.py:40-80`), `--server` from `COMFY_URL` (`:37`, `:79`);
  `main` builds `ComfyClient(args.server)` unless a transport is injected (`:127`), checks the faces group before
  any render (`:134-139`), and renders each prompt and count (`:149-172`). `ComfyClient` raises at once when the
  server does not answer (`synthetic_portraits/transport.py:198-199`).
- **`infra/up.sh`** creates on `rest.runpod.io/v1` (`:27`) with `:latest` (`:29`) and `~/.ssh/id_ed25519_runpod`
  (`:34`), the key on `curl`'s argv (`:128-135`), an HTTP proxy when `RUNPOD_EXPOSE_HTTP=1` (`:47-54`), a
  `desiredStatus` abort (`:203-209`). `infra/down.sh` deletes. `infra/start.sh` installs `PUBLIC_KEY`, starts
  sshd (`:12-21`), runs `/opt/download_models.sh` (`:24`), writes `extra_model_paths.yaml` and two symlinks
  (`:29-46`), and `exec`s ComfyUI (`:50`).
- **`download_models.sh`** (repository root) fetches its pinned files with `wget` into `MODELS_DIR`
  (`/runpod-volume/models`), each SHA-256 checked, a mismatch `exit 1` (`:71-82`).
- **The `Dockerfile`:** `FROM nvidia/cuda:12.8.1-cudnn-runtime-ubuntu22.04` by tag (`:11-12`), the system Python
  3.10; apt without `curl` (`:19-22`); `PermitRootLogin yes` and openssh's keys kept (`:79-80`); `COPY`s
  `constraints.txt`, `download_models.sh`, `infra/start.sh` (`:30`, `:83-84`); `CMD ["/opt/start.sh"]`, no
  `ENTRYPOINT` (`:93`).
- **`build-image.yml`:** dispatch, push to main and `v*` tags (`:6-12`); `latest` and `sha-*` tags (`:45-53`);
  a prune keeping one version (`:80-86`); actions on `@vN`.
- **The tests:** `tests/test_infra.py` reads the scripts' text and runs `up.sh` against a stub `curl`;
  `tests/test_faces.py:30`, `:90` reads `download_models.sh`'s pins; `tests/test_repo_hygiene.py:71-84` forbids
  a machine path in any tracked file.
- **`pyproject.toml`:** `requires-python = ">=3.11"`, `dependencies = []` (`:6-8`); `CLAUDE.md:104-110` — deps
  human-gated; pods announced, a "go", torn down.
- **gpunit `v0.2.0`:** `gpunit.session(spec, environ=, cwd=, say=)` yields `host`, `port()`, `ssh`, `image`,
  `pod_id`; raises `Refused`, `Lost`, `TeardownFailed`, `Interrupted`; tells the pod `GPUNIT_VOLUME_PATH`.
- **The precedent:** isekai's `isekai/boundary/gpu.py`, `isekai/interface/render.py`, `tools/image_record.py`,
  `isekai/boundary/pod_start.py`, `isekai/boundary/provision.py`.

## Goals / Non-Goals

**Goals:** a `--pod` batch over one session; no bash; the image pinned and recorded; no provider name in the code.

**Non-Goals:** outputs in memory; stripped metadata; a dead-container abort; any change to how a portrait renders.

## Decisions

| id | decision | because | rejected |
|---|---|---|---|
| [D1](#d1) | `--pod` on `generate.py`, exclusive of `--server`; one session around the whole batch | a batch is one command already | `gpunit run -- generate.py` |
| [D2](#d2) | `synthetic_portraits/gpu.py`: `read_env`, `open_session`; `gpunit` imported only inside it | one seam to fake; the stdlib-only import of the CLI holds | importing `gpunit` in `cli.py` |
| [D3](#d3) | the wait: `ComfyClient.system_stats()` polled every 5 s for 900 s; `session image:` printed on open | a cold volume downloads before ComfyUI starts; provenance in the run's log (Q14) | a sidecar file |
| [D4](#d4) | `gpunit.toml` committed; `gpunit` a runtime dependency; `.env` the key alone | the session's values reviewable | a gitignored spec |
| [D5](#d5) | `pod_start.py` and `provision.py` in the package, stdlib only, ruff `py310` for both | the image's Python is 3.10 | a second Python in the image |
| [D6](#d6) | `config/models.json` the manifest; `provision.py fetch` plans, transfers over `urllib`, verifies, lands | one record of the pins for the pod and the faces test | `wget` |
| [D7](#d7) | the image under `boot.sh`: `ADD --checksum`, `ENTRYPOINT`, `CMD ["python3", …/pod_start.py]`, `curl`, host keys deleted, telemetry off | gpunit is the stop, the key and sshd | keeping `start.sh`'s sshd |
| [D8](#d8) | `infra/` deleted with the proxy route; their tests deleted, their keys REMOVED | the tests read text that no longer exists | keeping dead tests |
| [D9](#d9) | `build-image.yml` on dispatch only, `latest` refused, no prune, actions by SHA; `config/image.json` the record, by `tools/image_record.py` | the prune deleted pinned images; a record shows drift | a build commit field |
| [D10](#d10) | README, `CLAUDE.md`, `.env.example` say gpunit; `CLAUDE.md` gains 45 minutes and ~$0.30 | a rule without a number is not a rule | — |
| [D11](#d11) | the last phase HUMAN · METERED: build `v0.6-rc1`, check the record, re-pin, one `--pod` batch | only a pod proves the pod | — |

### D1

```
parse ─▶ faces group present? ─▶ with open_session(...) as s:
            print "session image: <s.image>"
            client = ComfyClient(f"http://127.0.0.1:{s.port(8188)}")
            await system_stats, 900 s ─▶ render the batch as today
       ─▶ exit: the batch's code · 1 Refused, TeardownFailed (naming `uv run gpunit down`) · 3 Lost · 128+n Interrupted
```

`--pod` and `--server` are a mutually exclusive group; `--server` keeps its default from `COMFY_URL`.

### D2

`gpu.py` holds `read_env(path)` — `KEY=VALUE` lines, quotes stripped, comments and blanks skipped — and
`open_session(root, environ, say)`, which imports `gpunit` and returns `gpunit.session(root / "gpunit.toml",
environ=environ, cwd=root, say=say)`. `main` takes `open_session` as a keyword, as it takes `transport` and
`detector`; its tests pass a fake that yields a session and raises gpunit's exceptions. The environment handed
over is `os.environ | read_env(root / ".env")`.

### D3

`ComfyClient.system_stats()` is a `GET /system_stats` through the existing `_json`. The wait refuses with
`refused: the render server did not answer within 900s` and leaves the block, so the session closes.

### D4

```toml
project = "synthetic-portraits"
image = "ghcr.io/alxb1t/synthetic_portraits@sha256:<config/image.json's digest>"
gpus = ["NVIDIA RTX PRO 4500 Blackwell", "NVIDIA RTX PRO 4000 Blackwell", "NVIDIA GeForce RTX 4090", "NVIDIA L4"]
vram_gb = 24
cuda = "12.8"
disk_gb = 30
ports = [8188]
ceiling = "45m"
timeout = 600
volume = "<.env's RUNPOD_NETWORK_VOLUME_ID>"
```

Until the last phase builds an image under `boot.sh`, `image` and `config/image.json` carry a placeholder digest
of `0` × 64 that no pod can pull, so nothing renders before the re-pin. `pyproject.toml` adds `gpunit @
git+https://github.com/alxb1t/gpunit@v0.2.0` to `dependencies`, its comment naming the exception; `CLAUDE.md`'s
deps rule names it. `.gitignore` adds `.gpunit/`, drops `infra/.pod_id`, and stops calling the volume id a secret.

### D5

`synthetic_portraits/pod_start.py`: the volume (`GPUNIT_VOLUME_PATH` set), `<path>/models`, `extra_model_paths.yaml`
and the extensions' symlinks as `infra/start.sh:29-46` makes them, `provision.py fetch` as a subprocess, then
`os.execvp` into `python3 main.py --listen 0.0.0.0 --port 8188` in `/opt/ComfyUI`. A failed fetch exits `1`. Each
step prints `<UTC> step: …`. Both modules are copied to `/opt/sp/`; `pyproject.toml`'s ruff
`per-file-target-version` sets `py310` for them.

### D6

`config/models.json` holds `download_models.sh`'s entries: destination, source URL at its pinned revision,
SHA-256. `provision.py fetch [--models-dir DIR] [--manifest PATH]` skips a present file whose SHA-256 matches,
fetches the rest over `urllib` to `.partial`, verifies, and renames; a mismatch exits `1` naming both digests.
`tests/test_faces.py`'s pins test reads the manifest.

### D7

`Dockerfile`: `FROM nvidia/cuda:12.8.1-cudnn-runtime-ubuntu22.04@sha256:<digest>`; `curl` in apt; the openssh
layer ends `rm -f /etc/ssh/ssh_host_*`; the `PermitRootLogin` sed goes; `ENV ORT_DISABLE_TELEMETRY=1
HF_HUB_DISABLE_TELEMETRY=1 NO_ALBUMENTATIONS_UPDATE=1 DO_NOT_TRACK=1`; `COPY` the two modules and
`config/models.json`; `ADD --checksum=sha256:<boot.sh at v0.2.0>` gpunit's `boot.sh`; `ENTRYPOINT
["/opt/gpunit/boot.sh", "--"]`, `CMD ["python3", "/opt/sp/pod_start.py"]`.

### D8

`infra/up.sh`, `infra/down.sh`, `infra/start.sh` and `download_models.sh` are deleted. The tests of
`tests/test_infra.py` that read them go; the `Dockerfile` and constraints tests stay, rewritten where [D7](#d7)
moves a line. `RUNPOD_EXPOSE_HTTP`, the proxy hand-over, and README's and `.env.example`'s proxy paragraphs go.

### D9

`build-image.yml`: `on: workflow_dispatch` with a required `tag` input, `latest` refused; the metadata, prune and
cache steps go; actions pinned by commit SHA; the summary gets the digest and `python3 tools/image_record.py`.
`tools/image_record.py` prints the SHA-256 of `Dockerfile` and each `COPY` source, refusing a `COPY` it cannot read;
`config/image.json` holds `image`, `tag`, `digest`, `files`; a test holds `files` equal to the tree and `digest`
equal to `gpunit.toml`'s.

### D10

README's pod section becomes: `.env` with the key, `generate.py --pod --prompts …`, `uv run gpunit down` if a
session is left. `CLAUDE.md`: a pod is opened only by `--pod`, through gpunit; the ceiling is 45 minutes and
~$0.30 a session; the RunPod MCP confirms no `gpunit-synthetic-portraits` pod is left.

### D11

The operator pushes the branch, dispatches `build-image.yml` with tag `v0.6-rc1`, checks the summary's files equal
`config/image.json`'s, writes the tag and digest into `config/image.json` and `gpunit.toml`, runs `generate.py
--pod` on one prompt, and confirms through the RunPod MCP that no pod is left.

## Dependencies

- `gpunit @ git+https://github.com/alxb1t/gpunit@v0.2.0` — runtime: `--pod`'s GPU session. Stdlib only; nothing
  transitive. Approved in the grilling as the one exception to "no runtime deps" beside the `faces` group.

## Risks / Trade-offs

- **The pod's modules pass the gate on 3.11 but run on 3.10** → ruff's `py310` target for both; stdlib only.
- **A cold volume takes longer than 900 s** → the command refuses and closes the session; the next run finds the
  volume warm.
- **A copied file edited after the record** → the record's test goes red until the image is rebuilt and
  re-recorded.

## Verdict

Feasible: the lifecycle is gpunit's, the pod's steps are small, and the image's pin follows isekai's.
