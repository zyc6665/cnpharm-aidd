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

**Tool Contract**
: The platform-normalized description of a tool's identity, parameters, Standard Artifact inputs and outputs, resource needs, and allowed run surfaces.

**Tool Template**
: A reusable contract pattern for one class of scientific capability, such as protein preparation, molecular docking, ADMET prediction, or MD simulation.

**Resource Profile**
: A normalized estimate of the compute resources, runtime, timeout, and scheduling class required by a tool run.

**Executor Adapter**
: The Adapter that submits, observes, cancels, and collects a task run on one execution environment, such as Docker, SSH, K8s, Slurm, or Remote API.

**Workflow Input**
: A user-provided value or Artifact Binding promoted to the workflow level because a node requires it and no upstream node supplies it.

**Artifact Renderer**
: The viewer responsible for displaying one Standard Artifact type consistently across task details, Artifact details, workflow nodes, and result panels.
