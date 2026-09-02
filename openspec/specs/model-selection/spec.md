## Purpose

Let a caller choose which generation model renders a request, by name, and reject an unusable
choice locally rather than at paid GPU time.

## Requirements

### Requirement: Models are selected by registered name

The system SHALL resolve a model name to the graph and preparation logic that render it, SHALL
default to the prompt-only text-to-image model when no name is given, and SHALL reject an
unregistered name with an error listing the names that are available.

#### Scenario: The default model is the prompt-only text-to-image model

- **WHEN** no model name is given
- **THEN** the prompt-only text-to-image model is used
- **Key:** `models.default-is-txt2img`
- **Layers:** unit

#### Scenario: A registered name resolves to its graph and preparation

- **WHEN** a registered model name is looked up
- **THEN** it yields that model's graph file and the preparation logic for it
- **Key:** `models.registered-resolves`
- **Layers:** unit

#### Scenario: Every registered model's graph file exists

- **WHEN** the registry is enumerated
- **THEN** each registered model's graph file is present on disk
- **Key:** `models.graph-files-exist`
- **Layers:** unit

#### Scenario: An unknown name is rejected and the alternatives are named

- **WHEN** a model name that is not registered is requested
- **THEN** the invocation fails with an error that lists the registered names, before anything
  is queued
- **Key:** `models.unknown-rejected`
- **Layers:** unit, cli

### Requirement: The identity graph is not offered as a selectable model

The identity-preserving graph SHALL be selected only by supplying a reference image, never by
name. Selecting it by name would queue a graph whose image input still holds a placeholder — a
failure that would otherwise surface only on a running, billing GPU.

#### Scenario: Selecting the identity graph by name is rejected

- **WHEN** the identity graph's name is passed as the model
- **THEN** the invocation fails, because that name is not on the selectable menu
- **Key:** `models.identity-graph-off-menu`
- **Layers:** cli
