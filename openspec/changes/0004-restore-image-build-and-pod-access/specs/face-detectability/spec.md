## ADDED Requirements

### Requirement: A missing face-detection dependency is reported before any render is attempted

Face detection is an optional dependency group, and the command-line tool constructs a detector on every
run. When that group is not installed the tool SHALL fail with a clear, early error that names the
dependency group and the invocation that supplies it, rather than surfacing an import traceback for one
of the group's transitive modules.

The check SHALL happen before any work that depends on a running render server, because that server is a
metered GPU pod: the operator must learn that the dependency is missing while it is still free to fix,
not after the pod is up and billing.

#### Scenario: The missing dependency group is named, not the module that failed to import

- **WHEN** the command-line tool runs a render and the face-detection dependency group is not installed
- **THEN** it exits with an error naming the dependency group and how to supply it, rather than an
  unhandled import error for a transitive module
- **Key:** `faces.cli-missing-dep-named`
- **Layers:** unit

#### Scenario: The dependency is checked before the render server is contacted

- **WHEN** the command-line tool runs with the face-detection dependency group absent
- **THEN** it fails before submitting anything to the render server, so no metered work is started
- **Key:** `faces.cli-missing-dep-early`
- **Layers:** unit

#### Scenario: An injected detector needs no optional dependency

- **WHEN** a caller supplies its own detector
- **THEN** no check of the optional dependency group is performed, so the pipeline stays runnable with a
  stand-in and no test requires the group
- **Key:** `faces.cli-injected-detector-skips-check`
- **Layers:** unit
