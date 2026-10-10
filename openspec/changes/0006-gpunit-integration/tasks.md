# Tasks — 0006 gpunit integration

The configuration, `--pod`, the pod in Python, the scripts retired, the image pinned and recorded, the documents,
then the one metered proof, per [design](design.md). Every new test carries `@pytest.mark.spec` with the key its
task names.

## Progress

- [ ] 1 — The configuration
- [ ] 2 — --pod
- [ ] 3 — The pod in Python
- [ ] 4 — The scripts retired
- [ ] 5 — The image pinned and recorded
- [ ] 6 — The documents
- [ ] 7 — ⚠️ **HUMAN · METERED** — build, re-pin, one --pod batch

## 1 — The configuration

- [ ] 1.1 **HALT CHECK** — gpunit `v0.2.0` is on its remote, and the repository does not depend on it yet.
  Verify: `git ls-remote --tags https://github.com/alxb1t/gpunit v0.2.0 | grep -c 'refs/tags/v0.2.0$'` prints `1`, and `grep -c gpunit pyproject.toml` prints `0`.
- [ ] 1.2 Add `gpunit` to `pyproject.toml`'s `dependencies` with its comment naming the exception, and lock it with `uv lock`; name it in `CLAUDE.md`'s dependency rule; per [D4](design.md#d4).
  Verify: `grep -c 'gpunit @ git+https://github.com/alxb1t/gpunit@v0.2.0' pyproject.toml` prints `1`, and `grep -c 'name = "gpunit"' uv.lock` prints `1`.
- [ ] 1.3 Write `gpunit.toml` and `config/image.json` with the placeholder digest, the volume from `.env`'s `RUNPOD_NETWORK_VOLUME_ID`; add `.gpunit/` to `.gitignore` and drop its volume-id-as-secret wording; per [D4](design.md#d4). In `tests/test_infra.py` bind `pod.session-spec-pins`.
  Verify: `uv run python -c 'import gpunit; s = gpunit.load_spec(__import__("pathlib").Path("gpunit.toml")); print(s.project, s.ceiling_s, s.vram_gb)'` prints `synthetic-portraits 2700 24`, and `grep -c 'pod.session-spec-pins' tests/test_infra.py` prints `1`.

## 2 — --pod

- [ ] 2.1 Write `synthetic_portraits/gpu.py` per [D2](design.md#d2), and add `ComfyClient.system_stats()` to `synthetic_portraits/transport.py` per [D3](design.md#d3).
  Verify: `grep -c '^import gpunit\|^from gpunit' synthetic_portraits/gpu.py` prints `0`, and `grep -c 'def system_stats' synthetic_portraits/transport.py` prints `1`.
- [ ] 2.2 Add `--pod` to `synthetic_portraits/cli.py` per [D1](design.md#d1) and [D3](design.md#d3), with `open_session` injectable; in `tests/test_cli.py` bind `pod.session-closes-on-every-exit`, `pod.session-awaits-the-server`, `pod.session-names-its-image` and `pod.session-reads-env-whole` on a fake session.
  Verify: `grep -o -E 'pod\.session-[a-z-]+' tests/test_cli.py | sort -u | wc -l | tr -d ' '` prints `4`, and `uv run python generate.py --help | grep -c -- '--pod'` prints a number of at least `1`.

## 3 — The pod in Python

- [ ] 3.1 Write `config/models.json` from `download_models.sh`'s entries and `synthetic_portraits/provision.py` per [D6](design.md#d6); in `tests/test_provision.py` bind `pod.download-idempotent`, `pod.download-isolates`, `pod.download-pins-revisions` and `pod.download-verifies-sha256`; point `tests/test_faces.py`'s pins test at the manifest.
  Verify: `grep -o -E 'pod\.download-[a-z0-9-]+' tests/test_provision.py | sort -u | wc -l | tr -d ' '` prints `4`, and `grep -c 'download_models' tests/test_faces.py` prints `0`.
- [ ] 3.2 Write `synthetic_portraits/pod_start.py` per [D5](design.md#d5), and set ruff's `per-file-target-version` to `py310` for it and `provision.py` in `pyproject.toml`; in `tests/test_pod_start.py` bind `pod.start-maps-model-dirs` and `pod.start-stops-on-a-failed-provision`.
  Verify: `grep -c 'py310' pyproject.toml` prints a number of at least `1`, and `grep -c -E 'pod\.start-(maps-model-dirs|stops-on-a-failed-provision)' tests/test_pod_start.py` prints a number of at least `2`.
- [ ] 3.3 Rewrite `Dockerfile` per [D7](design.md#d7) but its `FROM` line; delete `infra/start.sh` and `download_models.sh`; in `tests/test_infra.py` drop them from `SHELL_SCRIPTS`, delete their tests, rewrite `test_dockerfile_launches_via_start_script` for the `ENTRYPOINT` and `CMD`, and bind `pod.telemetry-off`.
  Verify: `grep -c '^ENTRYPOINT \["/opt/gpunit/boot.sh", "--"\]$' Dockerfile` prints `1`, and `ls infra/start.sh download_models.sh 2>&1 | grep -c 'No such file'` prints `2`.

## 4 — The scripts retired

- [ ] 4.1 Delete `infra/up.sh` and `infra/down.sh`; delete the tests, helpers and `SHELL_SCRIPTS` of `tests/test_infra.py` that read them; drop `infra/.pod_id` from `.gitignore`; per [D8](design.md#d8).
  Verify: `ls infra 2>&1 | grep -c 'No such file'` prints `1`, and `find . -name '*.sh' -not -path './.venv/*' -not -path './.git/*' | wc -l | tr -d ' '` prints `0`.
- [ ] 4.2 Remove the proxy route from `README.md` and `.env.example`, `.env.example` down to `RUNPOD_API_KEY`, and reword the `User-Agent` reason in `synthetic_portraits/transport.py`, per [D8](design.md#d8).
  Verify: `grep -c -E 'RUNPOD_EXPOSE_HTTP|proxy\.runpod' README.md .env.example synthetic_portraits/transport.py | grep -v ':0$' | wc -l | tr -d ' '` prints `0`, and `grep -c 'RUNPOD_' .env.example` prints `1`.

## 5 — The image pinned and recorded

- [ ] 5.1 Pin the `Dockerfile`'s `FROM` by digest, and bind `pod.pins-base-by-digest` in `tests/test_infra.py`, per [D7](design.md#d7).
  Verify: `grep -c '^FROM nvidia/cuda:12.8.1-cudnn-runtime-ubuntu22.04@sha256:' Dockerfile` prints `1`.
- [ ] 5.2 Rewrite `.github/workflows/build-image.yml`, write `tools/image_record.py`, and fill `config/image.json`'s `files`, per [D9](design.md#d9); in `tests/test_infra.py` bind `pod.image-built-on-request`, `pod.image-record-matches-the-tree` and `pod.image-workflow-prints-the-record`, replacing the prune and `latest` tests.
  Verify: `python3 tools/image_record.py | python3 -c 'import json,sys; r=json.load(sys.stdin); print(r == json.load(open("config/image.json"))["files"])'` prints `True`, and `grep -c -E 'delete-package-versions|value=latest|@v[0-9]+$' .github/workflows/build-image.yml` prints `0`.

## 6 — The documents

- [ ] 6.1 Rewrite `README.md`'s pod section and `CLAUDE.md`'s spend rule per [D10](design.md#d10).
  Verify: `grep -c -E 'up\.sh|down\.sh|id_ed25519_runpod' README.md CLAUDE.md | grep -v ':0$' | wc -l | tr -d ' '` prints `0`, and `grep -c '45 minutes' CLAUDE.md` prints a number of at least `1`.

## 7 — ⚠️ **HUMAN · METERED** — build, re-pin, one --pod batch

- [ ] 7.1 **HUMAN · METERED** — push `v0.6_gpunit_integration`; dispatch `build-image.yml` on it with tag `v0.6-rc1`; check its printed files equal `config/image.json`'s `files`; write the tag and digest into `config/image.json` and the digest into `gpunit.toml`; run `uv run --group faces python generate.py --pod --prompt …` once; confirm through the RunPod MCP that no pod is left; per [D11](design.md#d11).
  Verify: `grep -c '"tag": "v0.6-rc1"' config/image.json` prints `1`, and `uv run gpunit status` prints `no session is recorded`.
