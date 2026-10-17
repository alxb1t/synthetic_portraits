## MODIFIED Requirements

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
