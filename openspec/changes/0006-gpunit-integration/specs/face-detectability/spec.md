## MODIFIED Requirements

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

- **WHEN** the pins used on a developer host are compared with the ones the pod's model manifest
  records
- **THEN** the revision and every digest agree, so both environments detect against identical
  model files
- **Key:** `faces.pins-agree-with-pod`
- **Layers:** structural
