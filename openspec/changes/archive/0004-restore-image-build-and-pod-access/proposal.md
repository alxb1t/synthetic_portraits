---
version: v0.4
---

## Why

**The published pod image has been un-buildable since 2026-08-10, and nobody knew.** `build-image` has
failed on every push to `main` since the v0.2 merge, so `ghcr.io/alxb1t/synthetic_portraits:latest` is
still the artefact built from `bb5bdda` — the commit *before* the custom nodes were added. A pod booted
from it has an empty `custom_nodes/`, so both shipped graphs fail at submit with
`Cannot execute because node UltralyticsDetectorProvider does not exist`. An attempt to render the twenty
portfolio portraits on 2026-09-09 produced **zero images** for ~$0.20 of pod time.

The cause is an internal contradiction introduced by `ca1669f`, the commit that pinned dependencies for
reproducibility: `constraints.txt` pins `numpy==1.26.4` (the Impact Pack ceiling) *and*
`opencv-python-headless==5.0.0.93`, which requires `numpy>=2`. The pinned set is exactly pinned and
mutually unsatisfiable, so pip ends in `ResolutionImpossible` every time. The existing requirement
`pod.constraints-fully-pinned` is *satisfied* by this file — which is precisely the gap: the repo checks
that pins are exact, never that they can all hold at once.

Two further defects were found in the same failed session, both of which cost money before they were
understood: `infra/up.sh` can leave a pod billing with no way in, and the CLI dies on a missing optional
dependency *after* the pod is already up.

## What Changes

- **The constraints contradiction is resolved.** `opencv-python-headless` moves from `5.0.0.93` to
  `4.11.0.86` — the version that accepts `numpy>=1.23.5`, and the one already pinned beside it as
  `opencv-python==4.11.0.86`. This is the one-line fix that makes the image buildable again.
- **The pinned set gains a consistency guard.** A new offline test parses `constraints.txt` and asserts
  the pins can hold together: the two OpenCV distributions agree on version, and the `numpy` pin stays
  below the Impact Pack ceiling. This runs inside the gate array, where `build-image` cannot.
- **`infra/up.sh` stops leaving pods billing.** Readiness becomes a bounded deadline that ends in
  teardown rather than a warning: 180 s waiting for a public IP, 420 s when falling back to the proxy,
  then `down.sh` is invoked automatically. Today's 300 s wait ends in a printed warning and a live pod.
- **Readiness polls the route actually in use.** With the HTTP port published, the render server
  answering on the proxy is readiness — the proxy needs no public IP, so it is reachable exactly in the
  condition where the tunnel's address never arrives. Waiting longer on the tunnel's signal alone tore
  down pods that were reachable. See `design.md` D7.
- **The HTTP proxy becomes opt-in, not a default exposure.** The uncommitted edit that adds
  `8188/http` unconditionally is **not** adopted as-is: it contradicts the shipped requirement
  `pod.up-enables-ssh` ("reached without exposing a public port"). The port is exposed only when
  `RUNPOD_EXPOSE_HTTP=1` is set, so the default remains tunnel-only. See `design.md` D3.
- **The transport sends an explicit `User-Agent`.** `Python-urllib/3.x` is refused by Cloudflare with
  error 1010, which is why the proxy answers `curl` and rejects the pipeline. One header on the existing
  `Request`; no dependency, and the runtime stays stdlib-only.
- **The CLI fails early when the `faces` extra is absent**, with a message naming
  `uv run --group faces`, instead of raising `ModuleNotFoundError: No module named 'cv2'` after a pod is
  running and billing.
- **`docs`: `README.md` records that the CLI — not only `scripts/check_face.py` — needs the `faces`
  group**, and that the tunnel is the only supported render path.

### Non-goals

- **Generating the twenty portfolio portraits is not part of this change.** That is a metered session
  against a working image, run once this change is released.
- **No render over the proxy is proven here.** The proxy *is* offered as the only route to a pod the
  provider issued no address for — that is what makes an otherwise-unreachable pod usable, and `design.md`
  D7 records it — but readiness over it is a GET to `/system_stats` and nothing more. Whether it accepts
  a `POST /prompt` would require a metered pod to prove, and the note that raised this is explicit that a
  `curl` status probe proved nothing last time. The hand-over says so in the same breath as it offers the
  URL. The tunnel remains the default and the path this project claims works.
- **`build-image` is not added to the gate array.** It needs a Docker daemon and cannot run on an offline
  checkout; the array's constraint is unchanged. The consistency test is what moves the checkable part of
  this failure *into* the array.
- **No boot-time node-presence assertion is added.** It was considered and set aside: it catches problems
  only after a pod is billing, and the constraints guard addresses the cause that actually occurred.

## Capabilities

### New Capabilities

None. Every change here tightens or corrects an existing capability.

### Modified Capabilities

- `gpu-pod-provisioning`: the pinned dependency set must be **mutually satisfiable**, not merely exactly
  pinned; pod readiness becomes a bounded deadline that tears the pod down on expiry, and it polls the
  access path actually in use rather than only the tunnel's; exposing the render server's HTTP port
  becomes explicit opt-in rather than unconditional.
- `comfyui-execution`: every request to the render server carries an explicit, non-default `User-Agent`.
- `face-detectability`: the CLI reports a missing face-detection dependency as a clear, early error
  naming the dependency group, rather than an import traceback.

## Impact

- **Code:** `constraints.txt` (the pin fix), `infra/up.sh` (deadline, teardown, opt-in port),
  `synthetic_portraits/transport.py` (the header), `synthetic_portraits/cli.py` (early failure),
  `README.md`.
- **Tests:** a new offline constraints-consistency test; transport tests for the header; a CLI test for
  the early failure. All offline — no test reaches a GPU or the network.
- **Dependencies:** none added. `opencv-python-headless` is *downgraded* within the existing pinned set.
- **Systems:** `build-image` returns to green, which republishes `:latest` with the custom nodes present
  for the first time since v0.2. The portfolio run is unblocked but not performed here.
- **Risk:** `opencv-python-headless==4.11.0.86` is an older OpenCV than the current pin. It is the version
  the sibling `opencv-python` pin already names, so the image converges on one OpenCV rather than two.
