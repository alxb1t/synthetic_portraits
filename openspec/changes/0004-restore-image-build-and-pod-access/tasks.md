# Tasks — 0004-restore-image-build-and-pod-access

Five phases as planned, plus **phase 6**, which was not planned: the readiness defect it fixes was found
in operation after phase 5 shipped, and it is recorded here rather than left as a commit with no task.
Each phase is independently committable, ends on a **green gate** (`make gate`, run and never
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
- [x] 6 — Readiness polls the access path in use (added after phase 5; found in operation)

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
      `uv run pytest -q -m spec` collects tests for all eleven new keys (ten at the time 5.2 was first
      run; phase 6 added `pod.up-polls-the-path-in-use` afterwards).
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

## 6. Readiness polls the access path in use

Design D7, which narrows D3. **Unplanned**: phases 1–5 were built and committed before this defect was
found, in operation, on 2026-09-09/10 in EU-RO-1. `RUNPOD_EXPOSE_HTTP=1` published the proxy port and
bought the longer deadline of D6, but the readiness loop still broke only on `publicIp` +
`portMappings["22"]` — so in the exact condition the flag exists for, it waited *longer* for an address
that would never arrive and then tore the pod down.

- [x] 6.1 Add a failing regression guard to `tests/test_infra.py`, marked
      `spec("gpu-pod-provisioning.pod.up-polls-the-path-in-use")`: with the HTTP port published, the
      readiness loop probes the proxy route and records a proxy-ready state. Verify: it fails against the
      pre-fix script — every assertion run against `0b3870c^`, not the file's prose. Commit `0b3870c`.
- [x] 6.2 Probe `${PROXY_URL}/system_stats` in the readiness loop when `EXPOSE_HTTP=1`, and hand the pod
      over on that route instead of tearing it down. `/system_stats`, not the bare host — the proxy
      resolves long before ComfyUI is listening (D7). Verify: the guard passes; `bash -n infra/up.sh`
      exits 0. Commit `0b3870c`.
- [x] 6.3 Add the scenario `pod.up-polls-the-path-in-use` to the `gpu-pod-provisioning` delta, and update
      5.2's count from ten new keys to eleven. Verify: `openspec validate
      0004-restore-image-build-and-pod-access --strict` is valid.
- [x] 6.4 `/simplify` pass over the fix. Verify: the rewritten guard fails on `0b3870c^` and passes on
      the fix — the original asserted the fix's comment rather than its behaviour. Commit `063b60c`.
- [x] 6.5 Record the decision. `design.md` gains **D7**; `proposal.md`'s non-goal and `.env.example` are
      reworded so the decision record no longer states the reverse of what `up.sh` does. Verify: `make
      gate` is green and `openspec validate --strict` is valid. (Converge round 1, finding R1.)
- [x] 6.6 `CHANGELOG.md` entry — landed with 6.2 under `Fixed` ("Pod readiness now polls the route
      actually in use"), which is where the EU-RO-1 measurement was first written down. Verify: `make
      gate` is green, then commit.
