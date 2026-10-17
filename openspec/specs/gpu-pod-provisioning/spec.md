## Purpose

Bring up, provision and tear down the on-demand GPU pod the renders run on, reproducibly, with
every model file verified before it is used and the pod's own identifier never committed.

## Requirements

### Requirement: The pod image pins every dependency it installs

The pod image SHALL pin its base image by digest, its CUDA and PyTorch build, its render-server extensions, and its Python
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
- **THEN** its entry point is gpunit's boot script, added at the tag `pyproject.toml` pins gpunit at with
  a checksum, and its command is the repository's start module, so a pod cannot start without the
  provisioning it performs
- **Key:** `pod.launches-via-start`
- **Layers:** structural

#### Scenario: The base image is named by digest

- **WHEN** the image definition is inspected
- **THEN** every image it builds from carries a digest, and every file it adds from a URL carries a checksum
- **Key:** `pod.pins-base-by-digest`
- **Layers:** structural

### Requirement: Model assets are fetched from immutable revisions and verified

Every model file the pod downloads SHALL come from a pinned, immutable revision and SHALL be
verified against a recorded SHA-256. A mismatch SHALL abort the download rather than continue.
Downloading SHALL be idempotent, so a restarted pod re-fetches nothing it already holds.

#### Scenario: Downloading is idempotent and covers the whole model set

- **WHEN** the provisioner runs against a volume that already holds the models
- **THEN** nothing is re-fetched, and every model the pipeline needs is accounted for
- **Key:** `pod.download-idempotent`
- **Layers:** structural

#### Scenario: Each model lands in its own target directory

- **WHEN** the provisioner runs
- **THEN** each model is written under the directory its consumer reads, not into a shared heap
- **Key:** `pod.download-isolates`
- **Layers:** structural

#### Scenario: Every source is pinned to an immutable revision

- **WHEN** the model manifest is read
- **THEN** every remote source is addressed by an immutable commit revision, never by a branch
  or tag that can move
- **Key:** `pod.download-pins-revisions`
- **Layers:** structural

#### Scenario: A digest mismatch aborts the download

- **WHEN** a downloaded file's SHA-256 does not match its recorded digest
- **THEN** the provisioner aborts rather than proceeding, and every file it fetches has a recorded
  digest to check against
- **Key:** `pod.download-verifies-sha256`
- **Layers:** structural

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

### Requirement: The start module exposes the model volume

The pod's start module SHALL point the render server's model directories at the persistent volume gpunit names
as `GPUNIT_VOLUME_PATH`, so models survive a pod being destroyed, and SHALL provision the models there before the
render server starts.

#### Scenario: The model directories are mapped onto the volume

- **WHEN** the start module runs
- **THEN** the render server's model directories resolve onto the persistent volume, including
  the ones the extensions hard-code
- **Key:** `pod.start-maps-model-dirs`
- **Layers:** unit

#### Scenario: A failed provisioning starts no render server

- **WHEN** the provisioner exits non-zero
- **THEN** the start module exits non-zero without starting the render server, so the boot script stops the pod
- **Key:** `pod.start-stops-on-a-failed-provision`
- **Layers:** unit

### Requirement: A batch renders on a pod through one gpunit session

With `--pod`, the command line SHALL open one gpunit session from the repository's `gpunit.toml`, handing gpunit
the process environment with the repository's `.env` read over it and naming no provider variable itself; SHALL
print the image the session booted; SHALL wait at most 900 seconds for the render server to answer through the
session's forwarded port; SHALL render the whole batch it was given; and SHALL close the session on every way
out. The session SHALL mount the working window's volume, which `gpunit volume up` makes and `gpunit volume down`
or the window's ceiling deletes, so a pod opened outside a window is refused before any create. Without `--pod`,
`--server` names the render server as before.

#### Scenario: Every exit closes the session

- **WHEN** a render raises, the render server never answers, or a signal arrives inside the session
- **THEN** the session's block is left and the session closes
- **Key:** `pod.session-closes-on-every-exit`
- **Layers:** unit

#### Scenario: The render server is awaited, within a bound

- **WHEN** the session is open
- **THEN** the render server's report is asked for through the forwarded port before any render
- **AND** after 900 seconds with no answer, the command refuses and the session closes
- **Key:** `pod.session-awaits-the-server`
- **Layers:** unit

#### Scenario: The session's image is printed

- **WHEN** the session opens
- **THEN** a line `session image: <reference>@<digest>` is printed to stderr, naming the image the session booted
- **Key:** `pod.session-names-its-image`
- **Layers:** unit

#### Scenario: The provider's key comes from the environment the command hands gpunit

- **WHEN** `.env` holds the provider's key and the process environment does not
- **THEN** the session opens with the key, and the repository's code names no provider variable
- **Key:** `pod.session-reads-env-whole`
- **Layers:** unit

#### Scenario: The session's spec pins the image and bounds the spend

- **WHEN** `gpunit.toml` is read
- **THEN** its image is a digest equal to the one `config/image.json` records, its ceiling is no longer than 45
  minutes, it asks for a window volume by its size and its ceiling and names no kept volume, and it asks for at
  least 24 GB of card memory and CUDA 12.8
- **Key:** `pod.session-spec-pins`
- **Layers:** structural

### Requirement: The image is built on request and recorded

The image SHALL be built only on a manual request naming a tag other than `latest`, SHALL never be pruned from
the registry by the workflow, and SHALL report its digest and the SHA-256 of the build file and of every file the
build copies. `config/image.json` SHALL record the same, and SHALL agree with the tree.

#### Scenario: Only a request builds, and nothing is pruned

- **WHEN** the image workflow is read
- **THEN** a manual request is its only trigger, `latest` is refused as a tag, and no step deletes a registry version
- **Key:** `pod.image-built-on-request`
- **Layers:** structural

#### Scenario: The build record agrees with the tree

- **WHEN** `config/image.json` is read beside the build file
- **THEN** it holds a SHA-256 for the build file and for every file the build file copies, each equal to the tree's
- **Key:** `pod.image-record-matches-the-tree`
- **Layers:** structural

#### Scenario: The workflow prints the record

- **WHEN** the image workflow is read
- **THEN** it writes the digest and the build record to its summary, from its own checkout
- **Key:** `pod.image-workflow-prints-the-record`
- **Layers:** structural

### Requirement: The pod sends no usage report its libraries can be told not to send

The image SHALL carry the telemetry and update-check switches of the libraries it runs, turned off.

#### Scenario: The image turns telemetry off

- **WHEN** the image definition is inspected
- **THEN** its environment turns off onnxruntime's and the Hugging Face hub's telemetry and albumentations' update
  check, and sets `DO_NOT_TRACK`
- **Key:** `pod.telemetry-off`
- **Layers:** structural
