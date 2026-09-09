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
