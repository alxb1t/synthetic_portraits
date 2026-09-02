## Purpose

Render a whole set of images from a file of prompts in one invocation, writing stable, sortable
filenames a caller can match back to the prompt that produced each one.

## Requirements

### Requirement: A prompt file renders one image per non-empty line

The system SHALL accept a file of prompts, one per line, and render the selected path once per
non-empty line. Blank lines SHALL be ignored. A missing file, a file with no prompts in it, and a
prompt file given together with a single prompt SHALL each be a usage error rather than a silent
no-op.

#### Scenario: A prompt file renders a set of independent people

- **WHEN** a prompt file of several lines is given with no reference image
- **THEN** one render is queued per line, carrying that line's text, and nothing is uploaded
- **Key:** `batch.independent-people`
- **Layers:** cli

#### Scenario: Blank lines are dropped

- **WHEN** a prompt file contains blank or whitespace-only lines
- **THEN** they produce no render, and surrounding whitespace is stripped from the rest
- **Key:** `batch.drops-blank-lines`
- **Layers:** unit

#### Scenario: A missing prompt file is a usage error

- **WHEN** the prompt file path does not name an existing file
- **THEN** the invocation fails with an error naming the path
- **Key:** `batch.missing-file-is-an-error`
- **Layers:** unit

#### Scenario: A prompt file with no prompts in it is a usage error

- **WHEN** the prompt file holds no non-empty line
- **THEN** the invocation fails with an error naming the file, rather than rendering nothing and
  succeeding
- **Key:** `batch.empty-file-is-an-error`
- **Layers:** unit, cli

#### Scenario: A single prompt and a prompt file together is a usage error

- **WHEN** both a single prompt and a prompt file are given
- **THEN** the invocation fails, because the prompt source must be unambiguous
- **Key:** `batch.sources-are-exclusive`
- **Layers:** cli

### Requirement: Batch output filenames are stable and derived from the prompt

Each image of a batch SHALL be written under a filename built from its position in the set and a
slug of its prompt, so the set sorts in prompt order and the same input file produces the same
names on every run. The slug SHALL be lowercase, filesystem-safe, bounded in length, and never
empty.

#### Scenario: A batch writes one stable, position-prefixed file per prompt

- **WHEN** a batch of prompts is rendered
- **THEN** each image is written as its prompt index, its repeat index and the prompt's slug
- **Key:** `batch.stable-filenames`
- **Layers:** cli

#### Scenario: A slug is lowercase and filesystem-safe

- **WHEN** a prompt is turned into a slug
- **THEN** the result is lowercase, holds only safe filename characters, and is the same for the
  same prompt every time
- **Key:** `batch.slug-is-stable`
- **Layers:** unit

#### Scenario: A slug is bounded and never empty

- **WHEN** a prompt is very long, or holds nothing that survives slugging
- **THEN** the slug is truncated to its bound, or falls back to a non-empty default
- **Key:** `batch.slug-truncates`
- **Layers:** unit

### Requirement: A batch combines with a reference image and with a per-prompt count

A prompt file SHALL compose with the other options: with a reference image it renders the same
person across every prompt, and with a count it renders that many images per prompt. Every element
of the resulting set SHALL receive its own seed, consecutive from the invocation's base seed, so a
fixed seed reproduces the whole set.

#### Scenario: A batch with a reference image is one person across every prompt

- **WHEN** a prompt file and a reference image are given together
- **THEN** every render uses the identity-preserving graph with the same uploaded reference, and
  each carries its own prompt
- **Key:** `batch.identity-character-sheet`
- **Layers:** cli

#### Scenario: A count multiplies the batch

- **WHEN** a prompt file of P lines is given with a count of N
- **THEN** P by N renders are queued and P by N distinctly named files are written
- **Key:** `batch.count-multiplies`
- **Layers:** cli

#### Scenario: Every element of the set gets a distinct, deterministic seed

- **WHEN** a batch is rendered from a fixed base seed
- **THEN** the seeds run consecutively across the whole set, in order, so the same base seed
  reproduces it
- **Key:** `batch.seeds-distinct-deterministic`
- **Layers:** cli
