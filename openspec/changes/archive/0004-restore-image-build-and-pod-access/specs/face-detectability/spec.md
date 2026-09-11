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

### Requirement: The detectability check runs by its documented invocation

The offline detectability check is a script, and a script is run the way its documentation says. Because
this repository is a virtual project, its package is never installed into the environment, and running a
file under a subdirectory puts that subdirectory — not the repository root — on the import path. The check
SHALL therefore make the package importable itself, so the invocation written in the documentation works
verbatim, with no environment variable and no change to how every other command resolves the package.

This SHALL be verifiable offline: the failure is an import, so it is reachable without the optional
face-detection dependency, without a model download and without a network.

#### Scenario: The check imports the package when run as a script

- **WHEN** the detectability check is executed as a file, with its own directory on the import path and
  from an unrelated working directory — what the interpreter does for the documented invocation
- **THEN** it imports the project's package successfully rather than raising a missing-module error
- **Key:** `faces.check-face-runs-as-documented`
- **Layers:** unit
