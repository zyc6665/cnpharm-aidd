# Domain Context

## Glossary

**Standard Artifact**
: A versioned scientific data object whose type, version, file roles, metadata, and validation rules are defined by the platform.

**Artifact Slot**
: A named tool input or output that references one Standard Artifact type, such as `protein_structure@1` or `binding_pocket@1`.

**Artifact Registry**
: The platform-owned catalog of Standard Artifact types, file roles, metadata schemas, validation rules, and compatibility rules.

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

**Binding Decision**
: The per-slot result produced during run preparation that explains whether an Artifact Slot is ready, missing, ambiguous, incompatible, or needs preparation or conversion.

**Run Preparation**
: The pre-run decision process that turns a Run Context, Tool Contract, user inputs, uploads, and upstream Artifacts into ready task inputs.

**Artifact Readiness**
: The usability of an ArtifactVersion for a specific Artifact Slot, based on type, version, roles, metadata, lifecycle state, cardinality, permission, and lineage.

**Tool Contract**
: The platform-normalized description of a tool's identity, parameters, Standard Artifact inputs and outputs, resource needs, and allowed run surfaces.

**Tool Template**
: A reusable contract pattern for one class of scientific capability, such as protein preparation, molecular docking, ADMET prediction, or MD simulation.

**Resource Profile**
: A normalized estimate of the compute resources, runtime, timeout, and scheduling class required by a tool run.

**Workflow Input**
: A user-provided value or Artifact Binding promoted to the workflow level because a node requires it and no upstream node supplies it.

**Artifact Renderer**
: The viewer responsible for displaying one Standard Artifact type consistently across task details, Artifact details, workflow nodes, and result panels.

**Renderer Registry**
: The platform-owned catalog that maps Standard Artifact types and roles to approved Artifact Renderers and preview/download capabilities.

**Result Manifest**
: The tool-produced declaration of output files, roles, metadata, checksums, and lineage that the platform can persist as Standard Artifacts.

**Artifact Lineage**
: The relationship between ArtifactVersions that records source, preparation, conversion, filtering, ranking, validation, or derivation.

**Run Surface**
: A user-facing entry point that starts a run, such as a tool detail page, a workflow node, a whole workflow, or an agent-approved plan.

**Node Task Binding**
: The saved association between a workflow node and the Task, outputs, and Artifact Bindings produced by that node's latest run.

**Tool Package**
: An immutable tool delivery package version that can be converted into a Tool Contract and then run through a concrete executor.

**Execution Record**
: The durable record of one low-level execution attempt for a Task on a concrete execution environment.

**Task View**
: A system-defined or user-saved perspective over Tasks, grouped and filtered by ownership, project, workflow, status, executor, time, Artifact type, or attention state.

**Saved View**
: A user-saved filter, grouping, sorting, and column layout for repeatedly reviewing Tasks, Artifacts, Tools, or Workflows.

**Tool Release**
: A reviewed ToolVersion that has passed contract validation, smoke testing, governance checks, and is available on selected run surfaces.

**Governance Registry**
: An administrator-managed catalog for configurable platform semantics such as tags, tool stages, workbench groups, Artifact roles, renderer mappings, executor profiles, and validation policies.

**Release Scope**
: The agreed set of capabilities, exclusions, acceptance scenarios, and feasibility assumptions that define what a platform version must deliver.

**Acceptance Baseline**
: The documented set of requirements, scale assumptions, test scenarios, and nonfunctional targets used to decide whether a delivery is complete.

**Plan Version**
: An immutable agent-generated plan snapshot that can be approved or rejected before becoming a WorkflowDefinition or Task.
