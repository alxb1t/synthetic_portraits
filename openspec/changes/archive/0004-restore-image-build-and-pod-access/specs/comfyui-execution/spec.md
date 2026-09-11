## ADDED Requirements

### Requirement: Every request to the render server identifies its client

The standard library's default user agent is refused by the edge proxy that fronts a pod when no
tunnelled route exists — the request is rejected before it reaches the render server, so a failure that
is purely about client identification appears as an unexplained transport error. Every request the
runtime makes to the render server SHALL therefore carry an explicit, non-default `User-Agent` header.

The header SHALL be applied uniformly across every call — submitting a graph, reading a result, fetching
an image and uploading one — so no single call path can be left with the default. Setting it SHALL NOT
introduce a third-party dependency; the runtime remains standard-library-only.

#### Scenario: Every request carries an explicit user agent

- **WHEN** the client submits a graph, reads a result, fetches an image, or uploads one
- **THEN** each request carries a `User-Agent` header that is set explicitly by the runtime, and none is
  left to the standard library's default
- **Key:** `comfy.sends-user-agent`
- **Layers:** unit

#### Scenario: The user agent does not displace the headers a request already needs

- **WHEN** a request that sets its own content type is built
- **THEN** that content type is still sent alongside the user agent, so adding the header changes no
  existing request semantics
- **Key:** `comfy.user-agent-preserves-content-type`
- **Layers:** unit
