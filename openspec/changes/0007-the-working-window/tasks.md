# Tasks — 0007 the working window

The pin with its boot script and record, the window and its documents, the image rebuilt, then one metered window,
per [design](design.md). No new test key: `pod.session-spec-pins` and `pod.launches-via-start` keep theirs.

## Progress

- [x] 1 — The pin
- [x] 2 — The window
- [ ] 3 — **HUMAN** — the image rebuilt and re-pinned
- [ ] 4 — ⚠️ **HUMAN · METERED** — one working window, a first and a second --pod run

## 1 — The pin

- [x] 1.1 **HALT CHECK** — `boot.sh` at gpunit `v0.7.0` has the checksum [D2](design.md#d2) names, and the repository still pins `v0.2.0`.
  Verify: `curl -fsSL https://raw.githubusercontent.com/alxb1t/gpunit/v0.7.0/boot/boot.sh | shasum -a 256 | cut -d' ' -f1` prints `517ade6bf20d9869baeb1f1ff1ab45d9ab63c2fa477127ff11dac89611bec842`, and `grep -c 'gpunit@v0.2.0' pyproject.toml` prints `1`.
- [x] 1.2 Pin gpunit at `v0.7.0` in `pyproject.toml` and relock with `uv lock --upgrade-package gpunit`, per [D1](design.md#d1).
  Verify: `grep -c 'rev=v0.7.0#e3b819b7d0951b0a99c2cab630e97ee2fabd059a' uv.lock` prints `1`, and `uv run python -c 'import gpunit; print(gpunit.__version__)'` prints `0.7.0`.
- [x] 1.3 `ADD` `boot.sh` from `v0.7.0` in `Dockerfile`, and move `tests/test_infra.py:298` and `:305` to `v0.7.0`, per [D2](design.md#d2).
  Verify: `grep -c 'ADD --checksum=sha256:517ade6bf20d9869baeb1f1ff1ab45d9ab63c2fa477127ff11dac89611bec842' Dockerfile` prints `1`, and `git grep -c 'v0\.2\.0' -- pyproject.toml uv.lock Dockerfile tests/test_infra.py | wc -l | tr -d ' '` prints `0`.
- [x] 1.4 Renew `config/image.json`: `files` from `python3 tools/image_record.py`, `tag` `""`, the `0` × 64 digest; put the same digest in `gpunit.toml`'s `image`; per [D3](design.md#d3).
  Verify: `python3 tools/image_record.py | python3 -c 'import json,sys; print(json.load(sys.stdin) == json.load(open("config/image.json"))["files"])'` prints `True`, and `grep -l 'sha256:0\{64\}"' gpunit.toml config/image.json | wc -l | tr -d ' '` prints `2`.

## 2 — The window

- [x] 2.1 In `gpunit.toml` replace `volume` with `volume_gb = 50` and `volume_ceiling = "4h"`; in `tests/test_infra.py` make `spec_faults`, its docstring, the comment at `:196` and its twin ask for the window; per [D4](design.md#d4).
  Verify: `uv run python -c 'import gpunit, pathlib; s = gpunit.load_spec(pathlib.Path("gpunit.toml")); print(s.volume, s.volume_gb, s.volume_ceiling_s)'` prints `None 50 14400`, and `grep -c '"no volume"' tests/test_infra.py` prints `0`.
- [x] 2.2 Write the order of commands, the window's 4 hours and ~$0.02, and the volume in the RunPod check into `CLAUDE.md`'s pod rule, per [D5](design.md#d5) and [D6](design.md#d6).
  Verify: `grep -c -E 'gpunit volume up --yes|gpunit volume down' CLAUDE.md` prints a number of at least `2`, and `grep -c '4 hours' CLAUDE.md` prints a number of at least `1`.
- [x] 2.3 Open README's `--pod` block with `volume up --yes` and end it with `volume down`; reword `README.md:48` and `:56` to the window volume's size and ceiling; per [D5](design.md#d5) and [D6](design.md#d6).
  Verify: `grep -c -E 'gpunit volume up --yes|gpunit volume down' README.md` prints a number of at least `2`, and `grep -c -E 'the ceiling, the volume\.|ceiling, the volume —' README.md` prints `0`.

## 3 — **HUMAN** — the image rebuilt and re-pinned

- [ ] 3.1 **HUMAN** — push `v0.7_the_working_window`; dispatch `build-image.yml` on it with tag `v0.7-rc1`; check its printed record equals `config/image.json`'s `files`; write the tag and digest into `config/image.json` and the digest into `gpunit.toml`; per [D7](design.md#d7).
  Verify: `grep -c '"tag": "v0.7-rc1"' config/image.json` prints `1`, and `grep -l 'sha256:0\{64\}' gpunit.toml config/image.json | wc -l | tr -d ' '` prints `0`.

## 4 — ⚠️ **HUMAN · METERED** — one working window, a first and a second --pod run

- [ ] 4.1 **HALT CHECK** — no session and no window is recorded before the window opens.
  Verify: `uv run --env-file .env gpunit status` prints `no session is recorded` and no `volume=` line.
- [ ] 4.2 **HUMAN · METERED** — announce, wait for a "go"; open a window, render into `outputs/v0.7-window-1` and `outputs/v0.7-window-2` on new pods, save the second pod's log as `outputs/v0.7-window-2/provision.log`, close the window; confirm through the RunPod MCP that no pod and no volume is left; per [D8](design.md#d8).
  Verify: `python3 -c 'import json; n = len(json.load(open("config/models.json"))["entries"]); log = open("outputs/v0.7-window-2/provision.log").read(); print(log.count("skip (present, verified)") == n, "fetching:" in log)'` prints `True False`, `ls outputs/v0.7-window-1/*.png outputs/v0.7-window-2/*.png | wc -l | tr -d ' '` prints a number of at least `2`, and `uv run --env-file .env gpunit status` prints `no session is recorded` and no `volume=` line.
