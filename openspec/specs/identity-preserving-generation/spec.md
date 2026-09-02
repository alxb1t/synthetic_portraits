## Purpose

Render the same synthetic person across many different prompts, from a single reference image of
that person, so a caller can build a character sheet rather than a set of strangers.

## Requirements

### Requirement: A reference face selects the identity path and is uploaded once

Supplying a reference (hero) image SHALL switch the render to the identity-preserving graph and
upload that image to the render server. The upload SHALL happen once per invocation, not once per
render attempt. Without a reference image, nothing SHALL be uploaded.

#### Scenario: A reference image switches the graph and uploads the hero

- **WHEN** a reference image is supplied
- **THEN** the identity-preserving graph is queued and the reference image's bytes are uploaded
  under its own filename
- **Key:** `identity.selects-graph-and-uploads`
- **Layers:** cli

#### Scenario: No reference image means no upload

- **WHEN** no reference image is supplied
- **THEN** the default prompt-only graph is queued and nothing is uploaded
- **Key:** `identity.no-hero-no-upload`
- **Layers:** cli

#### Scenario: A missing reference file is a usage error

- **WHEN** the reference image path does not name an existing file
- **THEN** the invocation fails with a usage error naming the path, before anything is queued
- **Key:** `identity.missing-hero-is-an-error`
- **Layers:** cli

#### Scenario: The reference image is uploaded once across regenerate attempts

- **WHEN** the regenerate loop makes several attempts for one image
- **THEN** the reference image is uploaded exactly once and reused by every attempt
- **Key:** `identity.upload-once-across-retries`
- **Layers:** unit

### Requirement: Uploaded images are wired to their graph nodes by role

Each uploaded image SHALL be wired to its target image-loading node by the role it was declared
under, matched against the node's own title, never by a hard-coded node id. A declared role with
no matching node SHALL be an error rather than a silently unwired graph.

#### Scenario: An uploaded image is wired onto the node for its role

- **WHEN** an image is uploaded under a role
- **THEN** the image-loading node whose title carries that role points at the uploaded name in
  the queued graph
- **Key:** `identity.wire-by-role`
- **Layers:** unit

#### Scenario: Role matching ignores case

- **WHEN** the node's title differs from the declared role only in letter case
- **THEN** it is still matched
- **Key:** `identity.role-match-case-insensitive`
- **Layers:** unit

#### Scenario: Declaring no inputs changes nothing

- **WHEN** there are no uploaded images to wire
- **THEN** the graph is left exactly as it was
- **Key:** `identity.empty-inputs-noop`
- **Layers:** unit

#### Scenario: A role with no matching node is rejected

- **WHEN** a declared role matches no image-loading node in the graph
- **THEN** preparation fails with an error naming the role, before anything is queued
- **Key:** `identity.unmatched-role-rejected`
- **Layers:** unit

### Requirement: The identity graph keeps positive and negative conditioning apart

The identity graph routes both conditionings through a shared node before the sampler. The system
SHALL still resolve each conditioning to its own encoder across that extra hop, so the prompt
never reaches the negative encoder, and SHALL place dimensions and seed exactly as on the default
path.

#### Scenario: The identity graph carries the identity legs

- **WHEN** the shipped identity graph is inspected
- **THEN** it contains the face-embedding and identity-application nodes, with the
  identity-application node sitting between the sampler and the text encoders
- **Key:** `identity.graph-has-instantid-legs`
- **Layers:** structural

#### Scenario: The prompt reaches the positive encoder across the extra hop

- **WHEN** an identity graph is prepared for a request
- **THEN** the prompt text is written to the positive encoder reached through the shared node
- **Key:** `identity.two-hop-positive`
- **Layers:** unit

#### Scenario: The prompt never leaks into the negative encoder

- **WHEN** an identity graph is prepared for a request
- **THEN** the negative encoder holds the negative text and not the prompt
- **Key:** `identity.two-hop-no-leak`
- **Layers:** unit

#### Scenario: Dimensions and seed still land on the identity graph

- **WHEN** an identity graph is prepared for a request
- **THEN** the width, height and seed are placed as they are on the default graph
- **Key:** `identity.two-hop-dims-and-seed`
- **Layers:** unit

#### Scenario: The identity path shares the default path's preparation

- **WHEN** the identity graph is looked up
- **THEN** it is prepared by the same graph-tracing logic as the default graph, not a parallel
  one
- **Key:** `identity.shared-injector`
- **Layers:** unit
