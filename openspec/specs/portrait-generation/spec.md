## Purpose

Turn one text prompt into a photoreal image of a person who does not exist, written to a local
output directory, with framing, seed and image count under the caller's control.

## Requirements

### Requirement: Render an image from a text prompt

The system SHALL accept a text prompt, render it on the configured render server, and write every
returned image into the caller's output directory.

#### Scenario: The prompt and its seed reach the queued graph

- **WHEN** a caller supplies a prompt and a seed
- **THEN** the graph submitted to the render server carries that prompt as its positive
  conditioning and that seed on its sampler
- **Key:** `portrait.prompt-and-seed-queued`
- **Layers:** cli

#### Scenario: Returned images are written to the output directory

- **WHEN** a render completes
- **THEN** the image bytes the server returned are written into the requested output directory,
  which is created if it does not exist
- **Key:** `portrait.saves-render`
- **Layers:** unit

#### Scenario: Every image the server reports is fetched

- **WHEN** a completed render reports more than one output image
- **THEN** each reported image is fetched from the server
- **Key:** `portrait.fetches-every-output`
- **Layers:** unit

### Requirement: Default framing is upper-body portrait, and is overridable

The system SHALL default to a portrait aspect suited to upper-body framing, and SHALL honour an
explicit width and height instead when the caller gives them.

#### Scenario: Omitting the dimensions gives the portrait default

- **WHEN** no width or height is given
- **THEN** the render is 832x1216
- **Key:** `portrait.default-dimensions`
- **Layers:** cli

#### Scenario: Explicit dimensions override the default

- **WHEN** a width and a height are given
- **THEN** the render uses those dimensions rather than the default
- **Key:** `portrait.dimension-overrides`
- **Layers:** cli

### Requirement: The default negative prompt guards anatomy without banning hands

Upper-body framing can show hands, so the default negative prompt SHALL suppress the anatomy and
non-photoreal failure modes without excluding hands from the image.

#### Scenario: Hands are not excluded

- **WHEN** the default negative prompt is used
- **THEN** it contains no term that would remove hands from an upper-body frame
- **Key:** `portrait.negative-allows-hands`
- **Layers:** unit

#### Scenario: The face guard is kept

- **WHEN** the default negative prompt is used
- **THEN** it still suppresses a poorly drawn face, which the downstream face stage depends on
- **Key:** `portrait.negative-guards-face`
- **Layers:** unit

### Requirement: Graph values are placed by tracing the graph, never by node id

Graphs are exported from a live render server and their node ids change between exports. The
system SHALL locate the nodes it writes to by following the graph's own links from its sampler,
so a re-exported graph with different ids still renders the caller's request.

#### Scenario: The prompt lands on the positive encoder

- **WHEN** a graph is prepared for a request
- **THEN** the prompt text is written to the encoder the sampler takes its positive conditioning
  from
- **Key:** `portrait.prompt-injected`
- **Layers:** unit

#### Scenario: The negative prompt lands on the negative encoder

- **WHEN** a graph is prepared for a request
- **THEN** the negative text is written to the encoder the sampler takes its negative
  conditioning from, and not to the positive one
- **Key:** `portrait.negative-injected`
- **Layers:** unit

#### Scenario: The dimensions land on the latent the sampler consumes

- **WHEN** a graph is prepared for a request
- **THEN** the width and height are written to the empty-latent node upstream of the sampler,
  even when an upscaling hop sits between them
- **Key:** `portrait.dimensions-injected`
- **Layers:** unit

#### Scenario: A renumbered graph still receives the request

- **WHEN** the same graph is presented with every node id changed
- **THEN** the prompt, dimensions and seed are still placed on the correct nodes
- **Key:** `portrait.injection-survives-renumbering`
- **Layers:** unit

#### Scenario: A pass-through conditioning node is followed by role

- **WHEN** a node that carries both conditionings sits between the sampler and its encoders
- **THEN** the trace follows the input named for the role it is resolving, keeping positive and
  negative apart
- **Key:** `portrait.injection-follows-role-through-passthrough`
- **Layers:** unit

#### Scenario: A graph with no sampler is rejected

- **WHEN** a graph contains no sampler node
- **THEN** preparation fails with an error naming the missing node, before anything is queued
- **Key:** `portrait.injection-rejects-graph-without-sampler`
- **Layers:** unit

#### Scenario: The stored graph is never mutated

- **WHEN** a graph is prepared for a request
- **THEN** the graph as read from disk is left unchanged, so the next request starts from the
  same source
- **Key:** `portrait.injection-does-not-mutate`
- **Layers:** unit

### Requirement: Seeds are reproducible and every image gets its own

A fixed seed SHALL reproduce a whole requested set. Each element of a set SHALL receive a
distinct, consecutive seed, and every sampling pass in the graph SHALL receive it, so re-seeding
re-rolls the whole person rather than part of the image.

#### Scenario: The seed is set on every sampling pass

- **WHEN** a graph contains more than one sampler pass
- **THEN** the request's seed is written to all of them
- **Key:** `portrait.seed-on-every-pass`
- **Layers:** unit

#### Scenario: A count renders that many images on consecutive seeds

- **WHEN** a count greater than one is requested with a fixed seed
- **THEN** that many images are rendered, on consecutive seeds counting from the given one
- **Key:** `portrait.count-consecutive-seeds`
- **Layers:** cli

#### Scenario: One image is rendered by default

- **WHEN** no count is given
- **THEN** exactly one image is rendered
- **Key:** `portrait.count-defaults-to-one`
- **Layers:** cli

#### Scenario: Omitting the seed still keeps a set internally consistent

- **WHEN** no seed is given
- **THEN** one random base seed is chosen for the whole invocation and the set's seeds are
  distinct and consecutive from it
- **Key:** `portrait.random-seed-consistent-within-run`
- **Layers:** cli

### Requirement: The shipped graph renders at high resolution and details the face

The graph the system ships SHALL run a second sampling pass over an upscaled latent and SHALL
apply face detailing as the last step before the image is saved, because the downstream consumer
reads the face.

#### Scenario: The second pass resamples the upscaled latent

- **WHEN** the shipped graph is inspected
- **THEN** its second sampler pass takes its latent from the upscaling node, not from the empty
  latent
- **Key:** `portrait.hires-pass`
- **Layers:** structural

#### Scenario: Face detailing is the last step before saving

- **WHEN** the shipped graph is inspected
- **THEN** the image the save node consumes comes from the face-detailing node
- **Key:** `portrait.face-detailer-last`
- **Layers:** structural

### Requirement: Invoked with no prompt source, the tool explains itself and succeeds

Running the tool with no prompt source SHALL print usage and exit zero rather than fail, so a
bare invocation is a discovery step and not an error.

#### Scenario: No prompt source prints usage and exits zero

- **WHEN** the tool is run with neither a prompt nor a prompt file
- **THEN** usage is printed and the exit code is zero
- **Key:** `portrait.no-prompt-prints-help`
- **Layers:** cli

#### Scenario: Asking for help exits cleanly

- **WHEN** help is requested
- **THEN** usage is printed and the process exits zero
- **Key:** `portrait.help-exits-zero`
- **Layers:** cli

#### Scenario: The documented entry point runs the tool

- **WHEN** the repository's documented entry point is invoked
- **THEN** it runs the same command-line interface, with the same arguments and exit code
- **Key:** `portrait.entry-point`
- **Layers:** unit
