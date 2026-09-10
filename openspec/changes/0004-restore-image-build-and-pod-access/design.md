## Context

See `proposal.md` — Why. The measurements behind that narrative are recorded here, because this is the
decision record and they live nowhere else.

**The build failure, from the CI log of run `33629035714` (2026-09-02):**

```
The conflict is caused by:
    The user requested numpy
    scikit-image 0.25.2 depends on numpy>=1.24
    transformers 5.14.1 depends on numpy>=1.17
    opencv-python-headless 5.0.0.93 depends on numpy>=2; python_version >= "3.9"
    The user requested (constraint) numpy==1.26.4
ERROR: ResolutionImpossible
```

The image is Python 3.10, so the `numpy>=2` marker applies. `numpy==1.26.4` and
`opencv-python-headless==5.0.0.93` cannot both hold.

**`numpy` requirement by `opencv-python-headless` version, read from PyPI metadata on 2026-09-09:**

| version | numpy requirement (`python_version >= "3.9"`) | compatible with `numpy==1.26.4` |
|---|---|---|
| `5.0.0.93` (current pin) | `numpy>=2` | no |
| `4.12.0.88` | `numpy>=2,<2.3.0` | no |
| `4.11.0.86` | `numpy>=1.19.3` (`>=1.23.5` for py3.11) | **yes** |

**Build history.** `:latest` is published only from `main` (`type=raw,value=latest,enable={{is_default_branch}}`).
The last green `main` build is `bb5bdda` at 2026-08-10T10:38:59Z. The very next `main` push, `d297ddb`
(the v0.2 merge that introduced the custom nodes, 10:40:17Z), failed, as did `679b7f8` on 2026-09-02.
So `:latest` predates the custom nodes entirely — which is exactly the empty `custom_nodes/` observed on
the pod, and it is not a stale-tag or a publish-race: it is one month of unbroken red.

**Constraint that shapes everything below:** the runtime package is stdlib-only and no test may reach a
GPU or the network. `build-image` is deliberately outside the gate array because it needs a Docker
daemon, which is why a build-only failure was invisible for a month.

## Goals / Non-Goals

**Goals:**

- Make the image buildable, and keep the *checkable* part of this class of failure inside the gate array.
- Make a pod that cannot be reached cost minutes rather than an unbounded amount.
- Make an optional-dependency failure cost nothing rather than a pod session.

**Non-Goals:**

- Reproducing pip's resolver offline. See D2 — the guard encodes the two traps this repository actually
  has, and does not attempt to be a general solver.
- Any claim that the HTTP proxy renders. It is offered as the only route to a pod that got no address,
  and it is verified by a GET; a render over it is not tested here. See D3 and D7.

## Decisions

### D1 — Fix the contradiction by moving OpenCV down, not numpy up

`opencv-python-headless` moves `5.0.0.93` → `4.11.0.86`.

*Alternative considered: raise `numpy` to `>=2`.* Rejected. The Dockerfile's own comment records that
`numpy` stays `<2` as the Impact Pack's ceiling, and the pack is what supplies `FaceDetailer` and
`UltralyticsDetectorProvider` — the nodes this whole change exists to restore. Moving `numpy` up would
trade a build failure for a runtime failure in the node that matters most, and would need a live pod to
disprove.

*Alternative considered: `4.12.0.88`.* Rejected — it also requires `numpy>=2`.

`4.11.0.86` is additionally the version already pinned as `opencv-python==4.11.0.86` in the same file, so
the fix converges the image on **one** OpenCV version instead of two. That the two pins had drifted apart
is the clearest signal that the contradiction was an oversight in `ca1669f` rather than a deliberate bump.

### D2 — The consistency guard encodes known traps, it does not resolve dependencies

The new test parses `constraints.txt` and asserts two properties: the two OpenCV distributions name the
same upstream version, and the `numpy` pin stays below the Impact Pack ceiling.

*Alternative considered: resolve the full set offline.* Rejected on the hard constraint — a real
resolution needs package metadata, which means a package index, which means the network. No test here may
touch it.

*Alternative considered: vendor the metadata.* Rejected as disproportionate: it would need refreshing on
every pin bump, and a stale copy would assert a fiction.

The honest framing, which the test's docstring carries: this is a **regression guard for a defect that
shipped**, not proof that the set resolves. Proof that the set resolves is `build-image`, and that job
already exists. What was missing was any signal inside the gate, and a narrow, exact assertion is a real
signal where an absent one was the actual failure.

### D3 — The HTTP port is opt-in, resolving a conflict with a shipped requirement

The uncommitted `up.sh` edit adds `8188/http` to the pod's ports unconditionally. That directly
contradicts the shipped scenario `pod.up-enables-ssh`, whose text is "the render server is reached
**without exposing a public port**". The provider's own documentation is quoted in the edit's comment:
the resulting URL is public, "the Pod ID provides only obscurity, not security", and ComfyUI has no auth.
Adopting the edit as written would silently weaken a security property that a requirement states.

The port is therefore published only when `RUNPOD_EXPOSE_HTTP=1`. The default path is unchanged and still
satisfies `pod.up-enables-ssh`; the new scenario `pod.up-http-port-opt-in` pins the default.

**D7 narrows this decision**: the opt-in default stands, but the proxy is no longer framed as
diagnostics-only — where the provider issues no address it is the only route, and it is offered as such.

*Alternative considered: drop the port entirely.* Rejected — it is the only route that works when the
provider issues no public IP, which is the failure that motivated the edit. Keeping it reachable behind
an explicit flag preserves the escape hatch without making public exposure the default.

*Alternative considered: adopt it unconditionally and amend `pod.up-enables-ssh`.* Rejected — the
operator's decision for this change was that the tunnel is the supported path. Making public exposure
unconditional would contradict that.

### D4 — The user agent is set once, on the request builder

Every request in the transport is constructed through `urllib.request.Request`. The header is applied at
that single construction point rather than per call site, so no path can be added later that silently
keeps the default. This is what the spec's uniformity scenario pins.

Cloudflare's 1010 is a user-agent block, so the value must not look like `Python-urllib/3.x`. It is a
browser-like value; that is the property being relied on, and the design records it plainly rather than
leaving a bare string to be read as arbitrary. No dependency is added — it is a header on a `Request` the
code already builds, and the runtime stays stdlib-only.

### D5 — The dependency check is explicit and precedes construction

`cli.py` calls `default_face_detector()` unconditionally, and `AntelopeV2FaceDetector` imports `cv2` and
`insightface` lazily inside its body — so the failure surfaces as `ModuleNotFoundError: No module named
'cv2'`, naming a transitive module rather than the group that supplies it.

The check runs only when no detector was injected. This keeps the seam intact: a caller that supplies a
stand-in — every test does — never triggers it, so the suite still needs nothing from the `faces` group.

*Alternative considered: catch `ModuleNotFoundError` and re-raise.* Rejected as fragile — it would also
catch an unrelated missing module inside the detector and mislabel it as a missing group.

### D6 — The readiness deadline ends in teardown, and the fallback gets longer

180 s for the tunnelled path, 420 s when HTTP exposure was requested, then `down.sh` is invoked. The
asymmetry is deliberate: a pod that will get a public IP does so quickly, whereas the proxy path is only
worth waiting on because ComfyUI must additionally finish starting behind it.

The values are adopted from the sibling isekai project, which reports converting four silent billing
failures into three-minute ones. They are recorded as adopted-from-a-sibling, not independently measured
here — this change does not spend a pod to calibrate them.

### D7 — Readiness polls the route in use, which makes the proxy an offered route (narrows D3)

D6 gave the proxy path a longer deadline while the readiness loop still broke only on `publicIp` +
`portMappings["22"]` — the tunnel's signal. So in the exact condition the flag exists for, the script
waited *longer* for an address that would never arrive and then tore the pod down. The extra 240 s
measured nothing it could change.

**Measurement (EU-RO-1, 2026-09-09/10, found in operation rather than review):** the region is
capacity-starved — `NVIDIA RTX PRO 4500 Blackwell` at LOW stock, cu12.8 Out — and two pods reached
`RUNNING` with `runtime: null`, never received a public IP or a port mapping, and were destroyed at the
180 s deadline. The proxy route needs no public IP and is reachable exactly in that condition.

The loop therefore also probes `${PROXY_URL}/system_stats` when the port is published, and a pod
reachable that way is handed over rather than destroyed. The probe is `/system_stats`, not the bare host:
the proxy resolves long before ComfyUI is listening, so anything less would report ready while a render
would still be refused. This is what `pod.up-polls-the-path-in-use` pins.

**What this narrows in D3.** D3 stands where it is load-bearing — the port is still opt-in, the default is
still tunnel-only, and `pod.up-enables-ssh` is still satisfied on the default path. What no longer holds
is D3's framing of the proxy as *diagnostics-only*. When the provider issues no address there is no
tunnel to prefer, so refusing the proxy would mean not rendering at all. The proxy is therefore stated
here as what it is: **opt-in, published only on request; public and unauthenticated for as long as the
pod lives; verified by a GET to `/system_stats`; and offered as the only route to that pod when no
address is issued.** What remains unproven is unchanged and is still stated at the hand-over: only GETs
are verified, and whether the proxy accepts a `POST /prompt` render has never been measured. Offering
the sole route to a pod the operator paid for is not the same claim as certifying it renders.

*Alternative considered: keep polling only the tunnel and let the pod be torn down.* Rejected by the
measurement — it destroys pods that are reachable, in the one region this project's network volume lives
in, and no amount of extra deadline can fix a signal that never arrives.

*Alternative considered: probe the bare proxy host.* Rejected — it answers before ComfyUI is listening,
so it would hand over a pod that refuses renders.

*Alternative considered: hand the proxy over without printing a `--server` command.* Rejected as
false modesty: it is the only route to that pod, and withholding the invocation would leave the operator
to reconstruct it while the pod bills. The unproven part is named in the same block instead.

Teardown reuses `down.sh` rather than issuing its own DELETE, so there is one code path that stops
billing and one place to get it right.

### D8 — A deadline is only as bounded as the calls inside it (narrows D6)

Raised by the converge security station (S1, S2) after D6 shipped, and fixed here rather than deferred
because both are billing exposures and both are one line.

D6 bounds readiness with a deadline tested **between** loop iterations. That makes the bound conditional
on every call inside the loop returning, and `curl` has no default transfer timeout — a half-open
connection through a NAT, or a provider-side stall, blocks inside the loop while `SECONDS` sails past
`ready_by`. `down.sh` is never reached and the pod bills for the length of the stall. The EXIT trap does
not rescue it: the trap runs when the script exits, and the script is not exiting. So every provider call
now carries `-m 30 --connect-timeout 10`, matching the `-m 10` the proxy probe already had. A timed-out
call then fails under `set -e`, which *is* an exit, which is the trap. `down.sh` is held to the same bar
for the sharper form of the same failure — a teardown that hangs tells the operator the pod is gone while
it is still billing — and its DELETE gains `|| true` so a timeout lands on the branch that names the
console instead of exiting silently.

The trap also has one window in front of it that it cannot cover: `POST /pods` may succeed server-side
while the id never reaches us, so `.pod_id` is never written and there is nothing to tear down *by*. No
trap can close that — the mitigation is to say it. The unreadable-id path now warns that a pod may exist
and names it for a console check, because an operator who reads "pod creation failed" as "nothing was
created" leaves a pod billing unattended.

*Alternative considered: a pre-create trap that looks the pod up by name and deletes a match.* Rejected
for this change — it makes teardown depend on name uniqueness across the account, and `up.sh` already
refuses to run while `.pod_id` exists, so the warning is proportionate to the residual risk.

*Alternative considered: leave both to the release backlog.* Rejected — they are the two findings that
cost real money, and neither needs a design change to fix.

## Risks / Trade-offs

- **The consistency guard passes while a different contradiction ships.** → Accepted and stated in the
  test's own docstring. It is a regression guard, not a resolver; `build-image` remains the real proof.
  Mitigated in practice by D1 converging the OpenCV pins, which removes the class of drift that occurred.
- **Automatic teardown destroys a pod that was about to become reachable.** → The deadlines are generous
  against observed behaviour, and a destroyed pod is recoverable by re-running `up.sh` for pennies,
  whereas an unreachable billing pod is not bounded at all. The asymmetry of cost favours tearing down.
- **`opencv-python-headless==4.11.0.86` is an older OpenCV.** → It is the version the sibling pin already
  names, so the image converges rather than regresses. No code here calls OpenCV 5 APIs; `cv2` is used
  only by the detector facade for image loading.
- **The user agent is a value chosen to pass a filter, and filters change.** → If the proxy stops
  answering, the tunnel is unaffected, which is why D3 keeps the tunnel the default. The cost of the
  filter changing is that the fallback route D7 offers stops being reachable — a pod torn down at the
  deadline, not a broken supported path.
- **`:latest` will change under any pod booted from it.** → That is the intent, and it is a strict
  improvement: the current image cannot execute either shipped graph. Verify with the full `/object_info`
  fetch before the first render, per the note that raised this.

## Migration Plan

No data migration. The sequence that matters is ordering, not state:

1. Land the constraints fix and the guard; the gate is green offline.
2. `build-image` republishes `:latest` on the push to `main` — the first image with the custom nodes.
3. Before the next real render, fetch the **full** `/object_info` and assert `UltralyticsDetectorProvider`
   and `FaceDetailer` are present. A per-node `GET /object_info/<NodeName>` returns 200 for absent nodes
   and proves nothing; this was measured on the failed 2026-09-09 session.

**Rollback:** revert the constraints commit. That restores a red build, so the meaningful rollback is
forward — the pre-change state is an image that cannot render at all.

## Open Questions

None that can be deferred. The one genuine unknown — whether the proxy accepts a `POST /prompt` once the
user agent is set — is deliberately unresolved and out of scope by D3 and D7: it requires a metered pod.
D7 offers the route where it is the only one and says plainly that only GETs are verified, so nothing in
this change depends on the answer.
