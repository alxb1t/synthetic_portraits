# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Entries are appended per phase under `## [Unreleased]`; the release cuts them into a
versioned section. The version declared by the active change, the heading here, the version
files and the annotated tag are one line — they agree, or the release halts.

## [Unreleased]

## [0.4.0] - 2026-09-11

### Changed

- **`README.md` records three things a failed session proved were missing.** The **CLI** needs
  `uv run --group faces`, not only `scripts/check_face.py` — the group is now step 0, before a
  pod is brought up, because a pod started first is already billing when the import fails. The
  **SSH tunnel is named as the only supported render path**, with `RUNPOD_EXPOSE_HTTP` written
  up as a public, unauthenticated, un-render-tested escape hatch. And `up.sh`'s self-teardown
  deadlines are stated where the pod is brought up.

### Fixed

- **`up.sh` is meant to fail fast when the container is dead instead of waiting out the deadline.** The
  readiness loop read only `publicIp` and `portMappings`, so a container that exited seconds after start
  looked exactly like one still coming up — three such pods each burned the full deadline. The same
  response carries the container's `desiredStatus` (the field the provider's published `Pod` schema
  defines; an earlier cut of this fix read a `status` that does not exist there, so it could never have
  fired), and the loop now aborts on `EXITED`/`TERMINATED` through the EXIT trap. **Not yet verified
  against a live pod** — the offline tests exercise the parser, not the provider. Fail-open: an absent
  status still means "keep waiting", so this cannot tear down a pod that would have come up.

- **`scripts/check_face.py` runs as documented again.** This is a virtual project
  (`[tool.uv] package = false`), so the package is never installed into the venv, and Python puts a
  script's own directory on `sys.path` rather than the repo root. That became fatal when the pinned
  antelopev2 staging import was added on 2026-08-10, and
  `uv run --group faces scripts/check_face.py …` has raised `ModuleNotFoundError` ever since — the
  unit tests never saw it because they inject a fake detector. The script now puts the repo root on
  `sys.path` itself.

- **`build-image` no longer deletes the image the pod pulls.** `latest` is tagged only on the default
  branch, but the "keep only the newest version" prune ran on every push — so running the workflow
  against a feature branch pushed a `sha-` tag and then deleted the only `latest` in the registry. Every
  pod created from `up.sh`'s default image reference then failed with `IMAGE_NOT_FOUND: manifest
  unknown`. The prune is now gated on the default branch, which is the only branch that can republish
  what it supersedes. Until a `build-image` run lands on `main`, pass
  `RUNPOD_IMAGE=ghcr.io/<owner>/synthetic_portraits:sha-<commit>` explicitly.

- **A pod can no longer bill through a stalled provider call.** The readiness deadline is tested between
  loop iterations, so it could only fire if every `curl` inside the loop returned — and `curl` has no
  default transfer timeout. A half-open connection or a provider-side stall blocked in the loop while the
  clock ran past the deadline: `down.sh` was never reached, and the EXIT trap could not help because the
  script was not exiting. Every provider call in `infra/up.sh` and `infra/down.sh` now carries
  `-m 30 --connect-timeout 10`, so a stall fails under `set -e` — which is an exit, which is the trap.
  `down.sh`'s DELETE additionally tolerates the timeout so it lands on the path that names the console,
  rather than exiting silently at the one moment the operator needs telling.

- **Pod creation that fails while reading the id now says a pod may exist.** `POST /pods` can succeed
  server-side while the id never reaches the client, which leaves no `.pod_id` for `down.sh` to delete
  and is the one window in front of the EXIT trap that no trap can cover. The path printed "pod creation
  failed", which an operator reasonably reads as "nothing was created" — while a pod billed unattended.
  It now warns explicitly and names the pod for a console check — **on every way out of that window**,
  not only the one where a response arrives. Under `set -euo pipefail` a `curl` that times out or is
  interrupted failed the assignment, so the script left *at that line*, in front of the branch carrying
  the warning and in front of every trap; adding a 30 s timeout to the create call made that the likelier
  failure. The warning is now a function reached from a checked create call, and a signal trap is
  installed before the request rather than after the id is known.

- **Pod readiness now polls the route actually in use.** `RUNPOD_EXPOSE_HTTP=1` published the
  proxy port but the readiness loop still waited only for a public IP — so in the exact
  condition the flag exists for, it waited *longer* for an address that would never arrive and
  then tore the pod down. Measured 2026-09-09/10: EU-RO-1 is capacity-starved (`RTX PRO 4500
  Blackwell` at LOW stock), and two pods reached `RUNNING` with `runtime: null` and were
  destroyed at the deadline while the proxy route could have served them. With the HTTP port
  published, the loop now also probes `<proxy>/system_stats` — the render server itself, not the
  bare host, which resolves long before ComfyUI is listening.

- **The pod image is buildable again.** `constraints.txt` pinned `numpy==1.26.4` (the Impact
  Pack's ceiling) alongside `opencv-python-headless==5.0.0.93`, which requires `numpy>=2`. The
  set was exactly pinned and mutually unsatisfiable, so every `build-image` run ended in
  `ResolutionImpossible`. `opencv-python-headless` moves to `4.11.0.86` — the version already
  pinned beside it as `opencv-python`, so the image now resolves one OpenCV rather than two.

  The consequence was not cosmetic: `build-image` had failed on every push to `main` since
  2026-08-10, so the published `:latest` was still the artefact built from the commit *before*
  the custom nodes were added. A pod booted from it had an empty `custom_nodes/`, and both
  shipped graphs failed at submit with `Cannot execute because node
  UltralyticsDetectorProvider does not exist`.

### Added

- **Every request to ComfyUI now carries an explicit `User-Agent`.** Cloudflare, which fronts
  a pod when no tunnelled route exists, answers the standard library's default
  `Python-urllib/3.x` with error 1010 — a user-agent block — so the request never reaches
  ComfyUI and the failure surfaces as an unexplained transport error. Measured 2026-09-09:
  `curl` received HTTP 200 where this client received 1010 against the same URL. The header is
  set at a single `Request` factory inside `ComfyClient`, so no call path can be added later
  that silently keeps the default. No dependency is added; the runtime stays stdlib-only.

  This makes the provider's HTTP proxy usable as a **diagnostic** channel. It is not a
  supported render path and has not been render-tested — the SSH tunnel remains the only
  path this project claims works.

- **The CLI reports a missing `faces` group before it queues anything.** `generate.py`
  constructs the real detector on every run, so without the optional group it died on
  `ModuleNotFoundError: No module named 'cv2'` — a transitive module that says nothing about
  the fix — and only *after* a metered pod was already up. It now fails with
  `face detection needs the optional 'faces' dependency group; re-run with
  'uv run --group faces python generate.py ...'`, naming the missing modules as detail.

  Presence is checked with `importlib.util.find_spec`, not by catching `ModuleNotFoundError`
  around construction: catching would also swallow an unrelated missing module raised from
  inside the detector and mislabel it. The check runs **only** when no detector was injected,
  so the seam is intact and no test needs the group.

- **`infra/up.sh` now tears down a pod it cannot reach.** Readiness was a 300 s wait that
  ended in a printed warning and a *live, billing* pod. RunPod repeatedly returned pods on
  2026-09-08/09 that reached `RUNNING` with `runtime: null`, no `publicIp` and no
  `portMappings` — reachable only over their SSH proxy, which cannot carry a port forward.
  The wait is now a bounded deadline (180 s tunnelled, 420 s when HTTP exposure is opted
  into) after which `down.sh` is invoked and the script exits non-zero. Teardown reuses
  `down.sh` rather than a hand-rolled DELETE, so one code path stops billing.

- **`RUNPOD_EXPOSE_HTTP`** — opt-in publication of ComfyUI's port on RunPod's HTTP proxy,
  **default off**. The proxy needs no public IP, so it is the only route that works when the
  tunnel cannot; it is also a public, unauthenticated URL fronting a ComfyUI with no auth,
  which is why it is a deliberate act rather than a default. Requirement `pod.up-enables-ssh`
  ("reached without exposing a public port") continues to describe the default path. The
  proxy remains a **diagnostic** channel and is not render-tested.

- **An offline consistency guard for the pinned set** (`tests/test_infra.py`). The existing
  `pod.constraints-fully-pinned` scenario is *satisfied* by a set pip cannot resolve, which is
  how the contradiction above shipped and stayed red for a month. Two new scenarios assert what
  that one cannot: the two OpenCV distributions name the same upstream version
  (`pod.opencv-pins-agree`), and the `numpy` pin can hold beside every other pin
  (`pod.constraints-mutually-satisfiable`). It is a regression guard, not a resolver — no test
  here may reach a package index, and `build-image` remains the real proof.

## [0.3.0] — 2026-09-02

### Added

- **A declared quality gate.** `.minions/minions.toml` carries the ordered `gate` array as
  the single source of truth, mirrored command-for-command by `Makefile`'s `gate` target
  and `.github/workflows/ci.yml`. `make gate` is the one command a human types. The array
  adds two axes the repo claimed but never ran in CI: `uv sync --locked` and
  `ruff format --check .`.
- **`.python-version`**, pinning 3.11 — the environment was resolving 3.12 while
  `requires-python`, `ruff target-version` and `ty python-version` all said 3.11.
- **`tests/test_repo_hygiene.py`** — four guards asserting no file in the tree contains the
  operator's home directory, this repository's own absolute root, or any reference to the
  external private notes directory the plan of record used to live in.
- **`tests/test_version_line.py`** — asserts the package's `__version__` and
  `pyproject.toml` agree, so the version line cannot silently drift again, and that every
  annotated tag has a changelog section (the tag list is derived from git, not hand-kept).
- **`tests/test_gate_mirrors.py`** — asserts the `Makefile`, `ci.yml`, `README.md` and
  `CLAUDE.md` restatements of the gate all equal the declared array, turning
  "change one, change all four" from an instruction into an enforced invariant.
- **The OpenSpec tree** (`openspec/`), with an authoring `config.yaml` whose context points
  at `CLAUDE.md` rather than restating it, and rules carrying only what an author cannot
  derive from that page.
- **This changelog.**
- **The living spec tree, backfilled.** `openspec/specs/` now describes what the pipeline
  already does, in seven capabilities — `portrait-generation`, `face-detectability`,
  `identity-preserving-generation`, `batch-generation`, `model-selection`, `comfyui-execution`
  and `gpu-pod-provisioning` — as 29 requirements and 100 scenarios, each carrying a stable
  `Key:` and the `Layers:` it is proved at. Every scenario is bound to a proving test by a
  `@pytest.mark.spec(...)` marker (100 keys, 100 bound, none orphaned in either direction);
  the repository's own structural guards keep `spec_exempt`. This is a description of current
  functionality, not a change to it: no behaviour changes, no test's meaning changes, and the
  change itself stays zero-delta rather than claiming to have `ADDED` capabilities that
  shipped in v0.1 and v0.2. Coverage gaps found while enumerating are recorded in the change's
  `design.md` rather than written as scenarios no test proves.

### Changed

- **`CLAUDE.md` rewritten to the standard template** — repo facts, not a script. The gate is
  now quoted verbatim from the declared array, the four seams that keep the suite offline
  are named, and a `## How a change is cut here` section states the four artifacts, the
  scaffold/author/validate commands and the `Change:` trailer rule. It points at
  `openspec instructions` and the `mf-*` skills for the rest of the method rather than
  restating a loop that would drift.
- **Lint adds the `D` and `ANN` selectors** on runtime code, with `tests/**` exempt from
  `D1`/`D401`/`ANN` by measurement. All 34 runtime violations fixed with real docstrings
  and honest annotations — `await_outputs`' injected clock is now
  `Callable[[float], None]`, and `workflow.py`'s three JSON node-input parameters are
  `object` rather than `Any`. `spec` and `spec_exempt` markers are registered but bind
  nothing yet.
- **The repository resolves no path outside itself.** The environment variable that pointed
  `.env.example` at an external private notes directory is gone, along with the references
  to it in the package docstring and `.gitignore`. The plan of record is in-repo, under
  `openspec/changes/`.
- **`README.md` states the gate** — `make gate` and the five commands in array order — and
  carries a current status line pointing at this changelog, replacing a stale note calling
  a shipped v0.2 feature an open item.

### Fixed

- **`uv.lock` was stale**: it recorded version `0.1.0` against a `pyproject.toml` of
  `0.2.0`, so v0.2.0 shipped with a lock that did not match and `uv sync --locked` failed
  on a clean checkout.
- **`synthetic_portraits.__version__` was stuck at `0.1.0`** while `pyproject.toml` said
  `0.2.0` — a second, unreferenced version declaration that had drifted a full release.
- **The repo-hygiene guard enumerated only tracked files**, so a newly written file passed
  the gate until its first commit and any violation in it surfaced a phase later. It now
  lists untracked-but-not-ignored files too, and so sees a file before it is committed.

## [0.2.0] — 2026-08-10

### Added

- **Identity preservation.** `--identity <image>` renders through an InstantID graph, so a
  single hero image drives a same-person character sheet across many prompts.
- **`--prompts <file>`** for character-sheet and batch runs, with a random default seed.
- **A `FaceDetector` facade and a regenerate loop** — a render is accepted only when it
  produced exactly one image holding exactly one antelopev2-detectable face; otherwise the
  KSamplers are re-seeded and it is rendered again, up to a budget.
- **Image-as-code support for InstantID and FaceDetailer**, with the custom nodes pinned.

### Changed

- **The default graph is hardened** with a latent hi-res pass and FaceDetailer, so a clean,
  detectable face survives any framing including full-height. Hi-res upscale tuned from
  bilinear to bislerp with denoise 0.45 → 0.55 and steps 20 → 25, after a live run showed
  the body softening while only the face sharpened.
- The internal identity graph is hidden from `--model`.

### Fixed

- **Custom-node model paths.** The Impact Subpack and the InstantID node resolve models from
  `folder_paths.models_dir` directly and ignore `extra_model_paths.yaml`, so the bbox list
  came up empty and InstantID auto-downloaded a broken nested antelopev2. `start.sh` now
  symlinks `models/{ultralytics,insightface}` onto the volume before ComfyUI launches.

### Security

- **S1 — model downloads are pinned and checksummed.** Every Hugging Face source in
  `download_models.sh` is pinned to an immutable commit SHA and SHA-256-verified after
  download, aborting on mismatch. Two of these weights are code-executing pickle from
  third-party mirrors, so a moved ref or a compromised mirror could otherwise have swapped
  in a file that loads on the pod. Verification also runs on the warm-volume skip path.
- **S2 — face and detailer PyPI dependencies are pinned** via `constraints.txt`, captured
  from the validated image, so an image rebuild resolves the same set rather than whatever
  PyPI serves that day.
- **S3 — antelopev2 is staged pinned and verified on the dev host.** The offline face gate
  used to let insightface auto-download the pack unpinned and unverified; each file is now
  fetched to a `.partial` and verified before it lands under its real name.

## [0.1.0] — 2026-08-10

### Added

- **The pipeline, end to end**: a text prompt renders a photoreal upper-body image of a
  person who does not exist, headless, via ComfyUI on an on-demand RunPod GPU.
- **The `ComfyTransport` seam** — a Protocol with a real stdlib-`urllib` client and an
  in-memory fake that replays `/prompt` → `/history` → `/view`, so no test reaches a GPU or
  the network.
- **Trace-based prompt injection** into the ComfyUI graph, plus a name→model registry.
- **Image-as-code**: a cu128 `Dockerfile`, pinned model downloads, `start.sh`, and a GHCR
  build workflow.
- **Pod lifecycle** — `infra/up.sh` and `infra/down.sh`, with SSH-tunnel access.
- **`scripts/check_face.py`** — the offline antelopev2 detectability assertion for the demo
  set.

### Changed

- **Pose is prompt-driven.** The OpenPose-ControlNet path was built and then removed: the
  prompt alone drove pose well enough that the extra graph, model and code did not earn
  their place.

[Unreleased]: https://github.com/alxb1t/synthetic_portraits/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/alxb1t/synthetic_portraits/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/alxb1t/synthetic_portraits/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/alxb1t/synthetic_portraits/releases/tag/v0.1.0
