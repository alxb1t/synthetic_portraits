## Purpose

Bring up, provision and tear down the on-demand GPU pod the renders run on, reproducibly, with
every model file verified before it is used and the pod's own identifier never committed.

## Requirements

### Requirement: The pod image pins every dependency it installs

The pod image SHALL pin its CUDA and PyTorch base, its render-server extensions, and its Python
dependencies to exact versions, so the same image definition builds the same environment. Face and
detail dependencies SHALL be installed CPU-only, so they claim no VRAM from the renderer.

#### Scenario: The CUDA and PyTorch base is pinned

- **WHEN** the image definition is inspected
- **THEN** it installs an exact PyTorch build against an exact CUDA version
- **Key:** `pod.pins-torch`
- **Layers:** structural

#### Scenario: The render-server extensions are pinned

- **WHEN** the image definition is inspected
- **THEN** each extension it installs is fixed to an exact revision rather than a moving branch
- **Key:** `pod.pins-custom-nodes`
- **Layers:** structural

#### Scenario: Face and detail dependencies are CPU-only and pinned

- **WHEN** the image definition is inspected
- **THEN** the face and detail dependencies, and the HTTP client the extensions need, are
  installed at exact versions and against the CPU runtime
- **Key:** `pod.pins-face-deps`
- **Layers:** structural

#### Scenario: The constraints file pins every line exactly

- **WHEN** the constraints file is read
- **THEN** every line names an exact version, with no range and no unpinned entry
- **Key:** `pod.constraints-fully-pinned`
- **Layers:** structural

#### Scenario: The image starts through the boot script

- **WHEN** the image definition is inspected
- **THEN** its entry point is the repository's boot script, so a pod cannot start without the
  provisioning it performs
- **Key:** `pod.launches-via-start`
- **Layers:** structural

### Requirement: Model assets are fetched from immutable revisions and verified

Every model file the pod downloads SHALL come from a pinned, immutable revision and SHALL be
verified against a recorded SHA-256. A mismatch SHALL abort the download rather than continue.
Downloading SHALL be idempotent, so a restarted pod re-fetches nothing it already holds.

#### Scenario: Downloading is idempotent and covers the whole model set

- **WHEN** the download script runs against a volume that already holds the models
- **THEN** nothing is re-fetched, and every model the pipeline needs is accounted for
- **Key:** `pod.download-idempotent`
- **Layers:** structural

#### Scenario: Each model lands in its own target directory

- **WHEN** the download script runs
- **THEN** each model is written under the directory its consumer reads, not into a shared heap
- **Key:** `pod.download-isolates`
- **Layers:** structural

#### Scenario: Every source is pinned to an immutable revision

- **WHEN** the download script is inspected
- **THEN** every remote source is addressed by an immutable commit revision, never by a branch
  or tag that can move
- **Key:** `pod.download-pins-revisions`
- **Layers:** structural

#### Scenario: A digest mismatch aborts the download

- **WHEN** a downloaded file's SHA-256 does not match its recorded digest
- **THEN** the script aborts rather than proceeding, and every file it fetches has a recorded
  digest to check against
- **Key:** `pod.download-verifies-sha256`
- **Layers:** structural

### Requirement: The boot script exposes the model volume and an operator login

The boot script SHALL point the render server's model directories at the persistent volume, so
models survive a pod being destroyed, and SHALL install the operator's public key so the pod is
reachable without a password.

#### Scenario: The model directories are mapped onto the volume

- **WHEN** the boot script runs
- **THEN** the render server's model directories resolve onto the persistent volume, including
  the ones the extensions hard-code
- **Key:** `pod.start-maps-model-dirs`
- **Layers:** structural

#### Scenario: The operator's public key is installed

- **WHEN** the boot script runs
- **THEN** the operator's public key is installed for the pod's login account
- **Key:** `pod.start-installs-ssh-key`
- **Layers:** structural

### Requirement: Pods are created and destroyed by script, and the pod identifier is never committed

Pod lifecycle SHALL be scripted against the provider's REST API: bringing one up records its
identifier locally and enables tunnelled access, and tearing it down deletes it. The recorded
identifier SHALL be untracked, because a pod that is running is a pod that is billing.

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

### Requirement: Every shell script is syntax-checked and fails fast

Every shell script in the repository SHALL parse cleanly and SHALL run under strict mode, so a
typo or an unset variable stops the script rather than provisioning a pod halfway.

#### Scenario: Every script parses cleanly

- **WHEN** each shell script is syntax-checked
- **THEN** it parses without error
- **Key:** `pod.scripts-syntax-clean`
- **Layers:** structural

#### Scenario: Every script runs under strict mode

- **WHEN** each shell script is read
- **THEN** it sets strict mode, so an error, an unset variable or a failed pipe stops it
- **Key:** `pod.scripts-strict-mode`
- **Layers:** structural

#### Scenario: The provisioning file set is present

- **WHEN** the repository is checked out
- **THEN** the image definition, the constraints file, the boot script, the download script and
  the pod lifecycle scripts are all present
- **Key:** `pod.infra-files-present`
- **Layers:** structural
