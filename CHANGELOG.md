# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Entries are appended per phase under `## [Unreleased]`; the release cuts them into a
versioned section. The version declared by the active change, the heading here, the version
files and the annotated tag are one line — they agree, or the release halts.

## [Unreleased]

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
  `pyproject.toml` agree, so the version line cannot silently drift again.
- **The OpenSpec tree** (`openspec/`), with an authoring `config.yaml` whose context points
  at `CLAUDE.md` rather than restating it, and rules carrying only what an author cannot
  derive from that page.
- **This changelog.**

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

[Unreleased]: https://github.com/alxb1t/synthetic_portraits/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/alxb1t/synthetic_portraits/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/alxb1t/synthetic_portraits/releases/tag/v0.1.0
