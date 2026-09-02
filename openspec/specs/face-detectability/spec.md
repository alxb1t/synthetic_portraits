## Purpose

Guarantee that every image this pipeline delivers holds exactly one detectable frontal face,
because the downstream face-identity consumer rejects zero-face and multi-face inputs.

## Requirements

### Requirement: A render is accepted only when it holds exactly one detectable face

The system SHALL count the detectable faces in each render and accept it only when the render is
a single image holding exactly one face. A render that is not accepted SHALL be re-seeded and
rendered again.

#### Scenario: A single-face render is accepted on the first attempt

- **WHEN** the first render holds exactly one detectable face
- **THEN** it is saved, no further render is queued, and the outcome reports one attempt
- **Key:** `faces.accept-one-face`
- **Layers:** unit

#### Scenario: An undetectable render is re-seeded and retried

- **WHEN** a render holds zero faces or more than one
- **THEN** the next attempt is rendered with the seed advanced by one, and the first render
  holding exactly one face is the one accepted
- **Key:** `faces.reseed-until-one-face`
- **Layers:** unit

### Requirement: The regenerate loop is bounded and never aborts the run

The regenerate loop SHALL stop after a bounded number of attempts. On exhaustion the system SHALL
keep and save the last render, report the failure, and continue — one stubborn prompt SHALL NOT
abort a batch or lose work.

#### Scenario: Exhausting the attempt budget keeps the last render

- **WHEN** no attempt within the budget holds exactly one face
- **THEN** the last render is still written to disk and the outcome reports the failure and the
  number of attempts made
- **Key:** `faces.exhausted-keeps-last`
- **Layers:** unit

#### Scenario: The attempt budget has a default

- **WHEN** no attempt budget is given
- **THEN** the loop makes at most five attempts
- **Key:** `faces.default-attempt-budget`
- **Layers:** unit

#### Scenario: An undetectable image is reported and fails the invocation

- **WHEN** at least one image in an invocation never reached one detectable face
- **THEN** a warning naming the seed and the attempt count is written to standard error, a
  summary counts the failures, and the exit code is non-zero
- **Key:** `faces.cli-reports-failure`
- **Layers:** cli

#### Scenario: An invocation whose images all passed is silent and succeeds

- **WHEN** every image in an invocation held exactly one detectable face
- **THEN** nothing is written to standard error and the exit code is zero
- **Key:** `faces.cli-silent-on-success`
- **Layers:** cli

### Requirement: Face detection is reached only through a swappable seam

Face detection is this runtime's one non-stdlib dependency. It SHALL be reachable only through an
interface that a caller can substitute, and merely importing the detection module SHALL NOT load
the detection libraries — so the package stays importable, and testable, without them installed.

#### Scenario: Importing the detection module loads nothing heavy

- **WHEN** the detection module is imported
- **THEN** no detection or computer-vision library is imported as a result
- **Key:** `faces.import-is-light`
- **Layers:** unit

#### Scenario: A substituted detector satisfies the seam

- **WHEN** a caller supplies its own face counter
- **THEN** it is accepted in place of the real detector and drives the regenerate loop
  unchanged
- **Key:** `faces.substitutable-detector`
- **Layers:** unit

### Requirement: The face model pack is pinned and verified before it is used

The detection model pack SHALL be staged from a pinned, immutable revision and every file
verified against a recorded SHA-256 before it is used, rather than auto-downloaded unpinned by
the detection library. Staging SHALL be idempotent, and SHALL leave nothing behind on failure.

#### Scenario: Each staged file is verified against its recorded digest

- **WHEN** the model pack is staged
- **THEN** every file is fetched from the pinned revision and its SHA-256 checked before it is
  put in place under its final name
- **Key:** `faces.pack-verified`
- **Layers:** unit

#### Scenario: An already-staged pack is left alone

- **WHEN** the pack is staged again and the files already present match their digests
- **THEN** nothing is re-fetched
- **Key:** `faces.pack-idempotent`
- **Layers:** unit

#### Scenario: A digest mismatch aborts and leaves nothing behind

- **WHEN** a fetched file's SHA-256 does not match the recorded digest
- **THEN** staging fails with an error naming the file and both digests, and the partial file is
  removed rather than promoted
- **Key:** `faces.pack-mismatch-aborts`
- **Layers:** unit

#### Scenario: The host pins and the pod pins are the same pins

- **WHEN** the pins used on a developer host are compared with the ones the pod provisioning
  script uses
- **THEN** the revision and every digest agree, so both environments detect against identical
  model files
- **Key:** `faces.pins-agree-with-pod`
- **Layers:** structural

### Requirement: Any set of images can be checked for detectability offline

An operator SHALL be able to assert the one-face guarantee over an arbitrary set of image files
without running the pipeline, and get an exit code that a script can act on.

#### Scenario: An image with exactly one face passes

- **WHEN** an image holds exactly one detectable face
- **THEN** it is reported as passing, with its face count
- **Key:** `faces.check-one-passes`
- **Layers:** unit

#### Scenario: An image with no face fails

- **WHEN** an image holds no detectable face
- **THEN** it is reported as failing
- **Key:** `faces.check-zero-fails`
- **Layers:** unit

#### Scenario: An image with several faces fails

- **WHEN** an image holds more than one detectable face
- **THEN** it is reported as failing
- **Key:** `faces.check-many-fails`
- **Layers:** unit

#### Scenario: A wholly passing set exits zero

- **WHEN** every checked image holds exactly one face
- **THEN** each image's result is printed, a total is summarised, and the exit code is zero
- **Key:** `faces.check-exit-zero`
- **Layers:** cli

#### Scenario: Any failing image fails the check

- **WHEN** at least one checked image does not hold exactly one face
- **THEN** the exit code is one
- **Key:** `faces.check-exit-one`
- **Layers:** cli

#### Scenario: Checking nothing is a usage error

- **WHEN** the check is invoked with no images
- **THEN** it says so and exits with a code distinct from both pass and fail
- **Key:** `faces.check-no-images`
- **Layers:** cli
