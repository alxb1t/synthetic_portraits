## Purpose

Carry every render out to the ComfyUI server and its images back — queue, wait, fetch — turning
server failures into clear errors instead of hangs, across a seam that lets the whole pipeline run
with no server present.

## Requirements

### Requirement: A render is queued and awaited until the server reports it complete

The system SHALL submit a prepared graph to the render server, then poll for that submission's
result until the server reports it, and return the outputs the server recorded.

#### Scenario: Polling continues while the result is still pending

- **WHEN** the server reports no result yet
- **THEN** polling continues, waiting between attempts, until the result appears
- **Key:** `comfy.polls-until-done`
- **Layers:** unit

#### Scenario: An already-complete submission returns without waiting

- **WHEN** the result is available on the first poll
- **THEN** the outputs are returned immediately, with no wait
- **Key:** `comfy.returns-immediately-when-done`
- **Layers:** unit

### Requirement: Server failures surface as errors, never as a silent hang

A submission the server rejects, a node that fails during execution, and a submission that never
completes SHALL each raise a distinct, described error. The error SHALL carry the server's own
detail where the server gave one.

#### Scenario: An execution failure is raised with the server's own detail

- **WHEN** the server reports that execution failed
- **THEN** an execution error is raised, naming the submission and quoting the server's failure
  message
- **Key:** `comfy.execution-error-surfaced`
- **Layers:** unit

#### Scenario: A submission that never completes times out

- **WHEN** the poll budget is exhausted with no result
- **THEN** a timeout error is raised naming the submission and the number of polls
- **Key:** `comfy.timeout`
- **Layers:** unit

#### Scenario: A rejected submission is an error

- **WHEN** the server refuses the graph at submission time
- **THEN** an execution error is raised carrying the server's validation detail, and no polling
  begins
- **Key:** `comfy.queue-rejection-is-an-error`
- **Layers:** unit

### Requirement: The server is reached over its HTTP interface using the standard library only

The runtime SHALL talk to the render server over HTTP with no third-party client: submitting a
graph, reading a submission's result, fetching a rendered image, and uploading an image as
multipart form data.

#### Scenario: Submitting posts the graph and returns its identifier

- **WHEN** a graph is submitted
- **THEN** it is posted as JSON to the server's prompt endpoint and the returned submission
  identifier is handed back
- **Key:** `comfy.queue-posts-and-returns-id`
- **Layers:** unit

#### Scenario: A submission's result is read as JSON

- **WHEN** a submission's result is requested
- **THEN** the server's history response is parsed as JSON and returned, empty while pending
- **Key:** `comfy.history-parsed`
- **Layers:** unit

#### Scenario: A rendered image is fetched as raw bytes

- **WHEN** an image named in a result is fetched
- **THEN** its filename, subfolder and folder type are sent to the server's view endpoint and
  the raw bytes are returned undecoded
- **Key:** `comfy.view-returns-bytes`
- **Layers:** unit

#### Scenario: An upload is sent as multipart form data

- **WHEN** an image is uploaded
- **THEN** it is posted as multipart form data under the image field, and the name the server
  stored it under is returned
- **Key:** `comfy.upload-multipart`
- **Layers:** unit

### Requirement: The server is reached across a substitutable seam

Every call to the render server SHALL go through one interface, so a caller can substitute an
in-memory stand-in and exercise the whole pipeline — including both failure paths — with no
server, no network and no GPU.

#### Scenario: The real client and a stand-in satisfy the same interface

- **WHEN** either the real client or an in-memory stand-in is checked against the interface
- **THEN** both satisfy it, and either can be handed to the pipeline
- **Key:** `comfy.seam-is-substitutable`
- **Layers:** unit

#### Scenario: The stand-in replays upload, submit and fetch

- **WHEN** the pipeline runs against the in-memory stand-in
- **THEN** the uploads, the submitted graphs and the fetched images are all recorded and
  inspectable, and no network call is made
- **Key:** `comfy.fake-replays-state-machine`
- **Layers:** unit
