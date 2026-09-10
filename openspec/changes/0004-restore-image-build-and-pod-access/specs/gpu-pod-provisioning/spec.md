## ADDED Requirements

### Requirement: The pinned dependency set is mutually satisfiable

Pinning every line exactly is not sufficient: an exactly-pinned set can still be internally
contradictory, in which case the image cannot be built at all. The constraints file SHALL therefore hold
a set of pins that can all be satisfied at once. Where two pinned distributions are alternative builds of
the same upstream project, they SHALL name the same upstream version. Where a pinned dependency imposes a
ceiling on another pinned dependency, the pinned version SHALL respect that ceiling.

This SHALL be checkable offline, from the repository alone, without a container runtime and without
contacting a package index — so that a contradiction is caught by the quality gate rather than by a
failed image build or, later, by a billing pod that cannot render.

#### Scenario: The two OpenCV distributions name the same version

- **WHEN** the constraints file is read
- **THEN** the headless and non-headless OpenCV distributions are pinned to the same upstream version,
  so the image resolves one OpenCV rather than two competing ones
- **Key:** `pod.opencv-pins-agree`
- **Layers:** structural

#### Scenario: The numeric-array pin respects the render extensions' ceiling

- **WHEN** the constraints file is read
- **THEN** the numeric-array library is pinned below the ceiling the render extensions require, and no
  other pinned distribution in the set demands a version above that ceiling
- **Key:** `pod.constraints-mutually-satisfiable`
- **Layers:** structural

### Requirement: Pod readiness is bounded and expiry tears the pod down

A pod that reaches a running state without becoming reachable is a pod that bills indefinitely for
nothing. Waiting for readiness SHALL therefore be bounded by a deadline, and reaching that deadline SHALL
destroy the pod rather than return control with it still running. The deadline SHALL be shorter when
waiting only for tunnelled access than when a fallback path is also being given a chance to answer.

#### Scenario: Waiting for readiness is bounded by a deadline

- **WHEN** the up script is inspected
- **THEN** its wait for a reachable pod is bounded by an explicit deadline, and the deadline allowed when
  a fallback path is in play is longer than the one for tunnelled access alone
- **Key:** `pod.up-bounded-readiness`
- **Layers:** structural

#### Scenario: An unreachable pod is destroyed rather than left billing

- **WHEN** the readiness deadline expires with the pod still unreachable
- **THEN** the up script destroys the pod before exiting, and reports that it did so
- **Key:** `pod.up-tears-down-on-timeout`
- **Layers:** structural

### Requirement: Readiness polls the access path actually in use

Waiting for a pod to become reachable SHALL test the route the operator will use, not a
different one. When only tunnelled access is requested, readiness is the provider issuing the
address and port that tunnel needs. When the render server's HTTP port has been published,
readiness SHALL also be satisfied by the render server answering on that published route,
because it needs no address of the tunnel's kind and is reachable exactly when that address is
never issued.

A deadline that waits longer for a fallback while still testing only the primary route measures
nothing the extra time can change: it tears down a pod that was, in fact, reachable.

#### Scenario: With the HTTP port published, the render server answering is readiness

- **WHEN** the render server's HTTP port has been published and the provider issues no address
  for tunnelled access, but the render server answers on the published route
- **THEN** the pod is reported ready over that route rather than torn down as unreachable
- **Key:** `pod.up-polls-the-path-in-use`
- **Layers:** structural

### Requirement: A create call that yields no pod identifier says a pod may exist

Creating a pod is the moment billing starts, and the identifier is what makes it stoppable. Between the
request leaving and an identifier being in hand there is a window no teardown can cover: the provider may
have created the pod while the client never learns its name for it, so there is nothing to destroy by and
no recorded identifier for the down script to read.

Every exit from that window — a request that fails in transport, a response carrying no identifier, and an
interrupt — SHALL therefore warn that a pod may nonetheless exist and name it, so the operator knows to
check the provider's console. Reporting only that creation "failed" is not sufficient: it reads as
"nothing was created", and an unattended pod bills until someone looks.

#### Scenario: A create call that yields no identifier warns that a pod may exist

- **WHEN** the up script's create call fails to produce a pod identifier — whether the call itself fails,
  the response carries no identifier, or the script is interrupted mid-request
- **THEN** it exits non-zero having warned that a pod may have been created anyway, naming the pod so the
  provider's console can be checked
- **Key:** `pod.up-warns-when-the-id-never-arrives`
- **Layers:** structural

### Requirement: Readiness aborts when the container is not running

A container that has died is not a container still starting. Waiting for readiness SHALL therefore read
the container's status out of the response it already fetches, and an explicitly terminal status SHALL end
the wait immediately, tearing the pod down by the same path the deadline uses rather than billing out the
rest of the deadline for a container that will never come up.

The status SHALL be read under the name the provider's published API schema defines. This check SHALL
fail **open**: any status that is not explicitly terminal — including no status at all — SHALL keep
waiting exactly as it would without this requirement, so a pod that would have become reachable is never
destroyed by it.

#### Scenario: A terminal container status ends the wait instead of billing it out

- **WHEN** the readiness response reports the container in a terminal state
- **THEN** the up script stops waiting and exits non-zero, so the pod is torn down, and it says the
  container is not running and that the image tag is the usual cause
- **AND** a response with no status keeps waiting, so the check cannot destroy a pod that would have
  become reachable
- **Key:** `pod.up-fails-fast-on-a-dead-container`
- **Layers:** structural

### Requirement: Publishing the image never deletes the image a pod pulls

The image workflow both publishes tags and prunes old versions from the registry. Pruning SHALL be
confined to the branch that can also republish what it deletes: off that branch a run deletes a tag it
cannot restore, and every pod created from the default image reference then fails to pull.

The image reference the up script pulls by default SHALL be a tag that workflow publishes, so the two
cannot drift apart unnoticed.

#### Scenario: The registry prune runs only on the default branch

- **WHEN** the image workflow runs on any branch other than the default one
- **THEN** the destructive prune step does not run, so the tag it could not republish survives
- **Key:** `pod.image-prune-is-default-branch-only`
- **Layers:** structural

#### Scenario: The pod's default image reference is a tag the workflow publishes

- **WHEN** the image workflow and the up script are read together
- **THEN** the tag the workflow publishes is the tag the up script pulls when no image is specified
- **Key:** `pod.image-branch-runs-keep-latest`
- **Layers:** structural

## MODIFIED Requirements

### Requirement: Pods are created and destroyed by script, and the pod identifier is never committed

Pod lifecycle SHALL be scripted against the provider's REST API: bringing one up records its
identifier locally and enables tunnelled access, and tearing it down deletes it. The recorded
identifier SHALL be untracked, because a pod that is running is a pod that is billing.

The render server's HTTP port SHALL NOT be published by default. Publishing it makes the render server
reachable at a provider URL that is public and unauthenticated, so it SHALL happen only when the operator
asks for it explicitly, and the default SHALL remain tunnelled access alone.

#### Scenario: The lifecycle scripts use the provider's REST API

- **WHEN** the pod scripts are inspected
- **THEN** they call the provider's REST API rather than a deprecated or unversioned interface
- **Key:** `pod.uses-rest-api`
- **Layers:** structural

#### Scenario: Bringing a pod up records its identifier

- **WHEN** the up script runs
- **THEN** a GPU pod is created and its identifier is written to a local state file the down
  script reads
- **Key:** `pod.up-persists-id`
- **Layers:** structural

#### Scenario: A pod that is up is reachable over a tunnel

- **WHEN** the up script runs
- **THEN** the pod is created with tunnelled access enabled, so the render server is reached
  without exposing a public port
- **Key:** `pod.up-enables-ssh`
- **Layers:** structural

#### Scenario: The render server's HTTP port is published only on request

- **WHEN** the up script runs without the operator opting in to HTTP exposure
- **THEN** only the tunnelled access port is requested from the provider, and the render server's HTTP
  port is not published
- **Key:** `pod.up-http-port-opt-in`
- **Layers:** structural

#### Scenario: Tearing down deletes the pod

- **WHEN** the down script runs
- **THEN** the recorded pod is deleted, so it stops billing
- **Key:** `pod.down-deletes`
- **Layers:** structural

#### Scenario: The recorded pod identifier is untracked

- **WHEN** the repository's ignore rules are checked
- **THEN** the pod state file is ignored, so a live pod's identifier is never committed
- **Key:** `pod.id-file-untracked`
- **Layers:** structural
