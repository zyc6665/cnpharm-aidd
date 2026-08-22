# Domain Context

## Glossary

**Standard Artifact**
: A versioned scientific data object whose type, version, file roles, metadata, and validation rules are defined by the platform.

**Artifact Slot**
: A named tool input or output that references one Standard Artifact type, such as `protein_structure@1` or `binding_pocket@1`.

**Run Context**
: The invocation scope for a tool or workflow run. It may point at a project, fall back to a user's default workspace, or remain file-only for runs that do not persist Standard Artifacts.

**Standalone Tool Run**
: A tool invocation started directly from the tool surface or a single canvas node, without requiring a workflow edge.

**Project Tool Run**
: A Standalone Tool Run whose Run Context is an explicit project.

**Workflow Run**
: A coordinated execution of tool nodes where Artifact Slots are bound from upstream nodes or workflow-level inputs.

**Artifact Binding**
: The decision that satisfies an Artifact Slot from an uploaded file, an existing ArtifactVersion, a workflow input, or an upstream node output.
