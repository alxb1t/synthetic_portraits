# Tasks — 0004-restore-image-build-and-pod-access

Five phases. Each is independently committable, ends on a **green gate** (`make gate`, run and never
summarized), a `CHANGELOG.md` entry, a ticked `## Progress` box and **one** commit whose message ends
with a `Change: 0004-restore-image-build-and-pod-access` trailer contiguous with any `Co-Authored-By:`
line.

`design.md` is authoritative for *how*; it is not re-derived here. Every unit of logic this project owns
is written **test-first (red → green)** — write the failing test, watch it fail for the stated reason,
then make it pass.

**The order of phases 1→5 is load-bearing.** Phase 1 is the only phase that unblocks anything: until the
constraints contradiction is resolved, no image can be built and every later phase ships into an artefact
that cannot run. Phase 5 is the only phase that touches money.

## Progress

- [x] 1 — The constraints fix and the offline consistency guard
- [x] 2 — The transport's explicit `User-Agent`
- [x] 3 — The CLI's early failure on a missing `faces` group
- [x] 4 — `infra/up.sh`: bounded readiness, self-teardown, opt-in HTTP port
- [x] 5 — Docs, spec binding, and the real image build

---

## 1. The constraints fix and the offline consistency guard

The blocking phase (design D1, D2). Test-first: the guard must **fail against the current
`constraints.txt`** before the pin is touched — that is what proves it would have caught `ca1669f`.

- [x] 1.1 Add the consistency test to `tests/test_infra.py`, marked
      `spec("gpu-pod-provisioning.pod.opencv-pins-agree")` and
      `spec("gpu-pod-provisioning.pod.constraints-mutually-satisfiable")`. It parses `constraints.txt`
      and asserts (a) `opencv-python` and `opencv-python-headless` name the same upstream version and
      (b) the `numpy` pin is `< 2`. Carry design D2's framing in the docstring: a regression guard, not a
      resolver. Verify: `uv run pytest -q tests/test_infra.py` **fails**, and the failure names the
      OpenCV version mismatch — not an import or parse error.
- [x] 1.2 Change `opencv-python-headless==5.0.0.93` → `==4.11.0.86` in `constraints.txt`. Verify:
      `uv run pytest -q tests/test_infra.py` now passes, and
      `grep -c 'opencv-python.*4\.11\.0\.86' constraints.txt` reports 2.
- [x] 1.3 Confirm the existing `pod.constraints-fully-pinned` scenario still holds — every line is still
      an exact pin. Verify: the full `uv run pytest -q` is green.
- [x] 1.4 `CHANGELOG.md`: add the `v0.4` Fixed entry naming the resolution failure and the month of red
      builds. Verify: `make gate` is green, then commit.

## 2. The transport's explicit `User-Agent`

Design D4. One construction point, so no call path can keep the default.

- [x] 2.1 Add failing tests to `tests/test_transport.py`, marked
      `spec("comfyui-execution.comfy.sends-user-agent")` and
      `spec("comfyui-execution.comfy.user-agent-preserves-content-type")`: assert every request the
      client builds carries a non-default `User-Agent`, across submit, history, view and upload, and that
      a request setting its own content type still sends it. Verify: `uv run pytest -q
      tests/test_transport.py` fails, naming the missing header.
- [x] 2.2 Set the header at the single `Request` construction point in
      `synthetic_portraits/transport.py`. Verify: those tests pass and the whole suite stays green.
- [x] 2.3 Confirm the runtime is still stdlib-only. Verify: `uv run python -c "import
      synthetic_portraits.transport"` succeeds with no third-party import, and `pyproject.toml`'s
      `dependencies` is still `[]`.
- [x] 2.4 `CHANGELOG.md` entry. Verify: `make gate` is green, then commit.

## 3. The CLI's early failure on a missing `faces` group

Design D5. The check runs only when no detector was injected, so the suite still needs nothing from the
optional group.

- [x] 3.1 Add failing tests to `tests/test_cli.py`, marked
      `spec("face-detectability.faces.cli-missing-dep-named")`,
      `spec("face-detectability.faces.cli-missing-dep-early")` and
      `spec("face-detectability.faces.cli-injected-detector-skips-check")`: with the group simulated
      absent, the CLI exits with an error naming the `faces` group and the `uv run --group faces`
      invocation, submits nothing to the transport, and performs no check at all when a detector is
      injected. Verify: `uv run pytest -q tests/test_cli.py` fails.
- [x] 3.2 Implement the guard in `synthetic_portraits/cli.py`, before any transport work and only on the
      non-injected path. Verify: those tests pass; the full suite is green.
- [x] 3.3 Verify the failure is early in the way that matters — the test asserting nothing reached the
      transport must be the one that proves it, not a comment.
- [x] 3.4 `CHANGELOG.md` entry. Verify: `make gate` is green, then commit.

## 4. `infra/up.sh`: bounded readiness, self-teardown, opt-in HTTP port

Design D3, D6. This phase **supersedes the two uncommitted edits currently in the working tree** — the
unconditional `8188/http` port is not adopted as written (D3). Review them, then replace.

- [x] 4.1 Add failing tests to `tests/test_infra.py`, marked
      `spec("gpu-pod-provisioning.pod.up-bounded-readiness")`,
      `spec("gpu-pod-provisioning.pod.up-tears-down-on-timeout")` and
      `spec("gpu-pod-provisioning.pod.up-http-port-opt-in")`: `up.sh` declares both deadlines with the
      fallback longer than the tunnelled one, invokes `down.sh` on expiry, and requests only the
      tunnelled port unless `RUNPOD_EXPOSE_HTTP` is set. Verify: `uv run pytest -q tests/test_infra.py`
      fails.
- [x] 4.2 Rewrite the readiness loop in `infra/up.sh`: 180 s tunnelled / 420 s with HTTP exposure, then
      invoke `down.sh` (never a hand-rolled DELETE — D6) and exit non-zero. Verify: the deadline tests
      pass.
- [x] 4.3 Gate the `8188/http` port behind `RUNPOD_EXPOSE_HTTP=1`, defaulting off, keeping the proxy URL
      printed only when it was requested. Verify: the opt-in test passes and the existing
      `pod.up-enables-ssh` scenario still holds.
- [x] 4.4 Confirm the script still parses and is strict-mode. Verify: `bash -n infra/up.sh` exits 0 and
      the existing `pod.scripts-syntax-clean` / `pod.scripts-strict-mode` tests are green.
- [x] 4.5 Add `RUNPOD_EXPOSE_HTTP` to `.env.example`, documented as public and unauthenticated, default
      off. Verify: `.env.example` stays path-free — the existing hygiene test is green.
- [x] 4.6 `CHANGELOG.md` entry. Verify: `make gate` is green, then commit.

## 5. Docs, spec binding, and the real image build

The only phase that leaves the repository. It spends no GPU: `build-image` is CI, not a pod.

- [x] 5.1 `README.md`: record that the **CLI** needs `uv run --group faces`, not only
      `scripts/check_face.py`; that the SSH tunnel is the only supported render path; and that
      `RUNPOD_EXPOSE_HTTP` publishes a public, unauthenticated endpoint. Verify: `make gate` is green.
- [x] 5.2 Confirm every scenario `Key:` introduced by this change is bound to a marked test. Verify:
      `uv run pytest -q -m spec` collects tests for all ten new keys.
- [x] 5.3 Run the real image build against this branch — `gh workflow run build-image.yml --ref
      <branch>`, then `gh run watch`. Verify: the run **succeeds**, which is the first green
      `build-image` since 2026-08-10 and the proof that D1 resolved the contradiction. **This is the
      phase's load-bearing verification** — the gate cannot prove it.
- [x] 5.4 Verify the built image actually carries the nodes, without booting a pod: pull the image
      produced by 5.3 and list `/opt/ComfyUI/custom_nodes/`. Verify: `ComfyUI-Impact-Pack`,
      `ComfyUI-Impact-Subpack` and `ComfyUI_InstantID` are all present — the condition whose absence
      started this change. If no Docker daemon is available locally, record that this was deferred to the
      `/object_info` check in the migration plan rather than marking it done.
- [x] 5.5 `CHANGELOG.md`: close the `v0.4` entry. Verify: `make gate` is green, then commit.
