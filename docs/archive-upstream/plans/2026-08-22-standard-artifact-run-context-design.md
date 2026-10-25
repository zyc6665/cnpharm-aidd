# Standard Artifact Run Context Design

## Problem

The platform already has versioned Standard Artifacts and tool contracts, but the current user experience mixes three different concerns:

1. Tool contracts describe scientific inputs and outputs.
2. Project context controls where existing Artifacts are searched and where new Standard Artifacts are persisted.
3. Workflow edges decide how upstream outputs satisfy downstream inputs.

Because these concerns are not separated cleanly, the tool detail page currently blocks tools with Standard Artifact inputs unless `project_id` is present, while the backend already supports optional `project_id` for task creation and can resolve a default project for Standard Artifact outputs. The result is a confusing rule: tools feel project-only even when they should be usable independently.

## Domain Model

The platform should use these concepts consistently:

- **Tool Contract**: what the tool needs and produces. It owns `parameters_schema`, `artifacts.inputs`, and `artifacts.outputs`. It must not require deployment or project context.
- **Run Context**: where a run happens. It may be an explicit project, a user default workspace, or file-only when no Standard Artifact is emitted.
- **Artifact Slot**: a named Standard Artifact input or output, such as `protein` accepting `protein_structure@1`.
- **Artifact Binding**: the resolved source for an input slot. It can come from an existing ArtifactVersion, an uploaded file, a workflow input, or an upstream node output.

This keeps the tool interface small and deep: callers provide a tool, a run context, and input sources; the platform handles validation, conversion, binding, persistence, and workflow compatibility.

## Recommended Architecture

Introduce a shared Artifact Binding Resolver as the deep module behind all tool invocation surfaces.

Its interface should be intentionally small:

```ts
resolveArtifactBindings({
  toolContract,
  runContext,
  parameterValues,
  selectedArtifacts,
  uploadedFiles,
  workflowSources,
})
```

The resolver returns:

- normalized task `params`
- `file_ids`
- Standard ArtifactVersion `input_bindings`
- binding decisions for UI and task logs
- missing input or preparation issues
- the resolved output project, if Standard Artifacts will be persisted

Backend and frontend do not need identical code, but they should expose the same model. Frontend uses it for form state, preflight, and user guidance; backend is the authority for validation and task submission.

## Run Modes

### Standalone Tool Run Without Project

Users can run a tool directly from the tool detail page or a canvas node without `project_id`.

- Parameter fields render normally.
- Standard Artifact input slots allow upload/staged files.
- Existing project Artifact selection is hidden or shown as unavailable with an action to enter a project.
- If the tool emits Standard Artifact outputs, backend resolves a user default project/workspace and persists outputs there.
- If the tool emits only legacy files or scalar JSON, no project is required.

### Standalone Tool Run With Project

Users enter from a project route or URL with `project_id`.

- Standard Artifact slots can bind compatible project ArtifactVersions.
- Users can still upload files for slots when no existing Artifact is suitable.
- Outputs persist into the selected project.
- Binding decisions record selected file roles and readiness status.

### Workflow Run

Users should drag nodes and connect them. They should not manually map low-level fields for normal cases.

- Downstream Artifact Slots are satisfied by upstream Standard Artifact outputs when edge types match.
- Workflow-level inputs are requested only when no upstream node supplies a required slot.
- Existing ArtifactVersion inputs require a project-scoped workflow run.
- If the workflow has Standard Artifact outputs and no explicit project, backend resolves the user's default project/workspace at run start.
- Preparation policy, role preferences, and required roles stay in the slot contract, not in node-specific UI hacks.

## Contract Rules

Tool authors must declare three separate surfaces:

```yaml
parameters_schema:
  type: object
  properties:
    threshold:
      type: number

artifacts:
  inputs:
    - name: protein
      type: protein_structure@1
      required: true
      role_preferences: [prepared_pdb, structure_file]
      readiness_policy: prefer_prepared_warn_raw
      suggested_preparation_tool: builtin-protein-preparation
  outputs:
    - name: pocket
      type: binding_pocket@1
      required: true
      cardinality: one
```

Rules:

- `parameters_schema` is for scalar/UI parameters only.
- `artifacts.inputs` is for data inputs that can be uploaded, selected, or auto-bound.
- `artifacts.outputs` is fixed to platform Standard Artifact types.
- Project identity is invocation context, never part of the tool contract.
- New tools should not require workflow-specific adapters when their Artifact Slots are valid.

## User Experience

Replace the current hard warning with context-aware controls:

- No project and Standard inputs: show upload controls first, plus a secondary message: “进入项目后可直接选择已有 Artifact”。
- Project present: show compatible project ArtifactVersions first, with upload as fallback.
- Workflow canvas: show required inputs only at workflow boundary, not on every connected downstream node.
- Preflight should distinguish missing uploaded file, missing project Artifact binding, upstream waiting, and preparation needed.

## Error Handling

- Existing ArtifactVersion binding without a project context should fail with: “选择已有 Artifact 需要项目上下文；请进入项目或改为上传文件。”
- Standard output persistence without explicit project should resolve the default workspace project server-side.
- If no default workspace can be created, fail before dispatch with an actionable message.
- If slot role requirements are not met, return binding decisions with `status`, `reason`, and suggested preparation tool.
- Workflow semantic mismatches should cite source slot, target slot, and Standard Artifact type.

## Testing Strategy

- Unit-test frontend resolver behavior for project/no-project/upload/existing Artifact cases.
- Unit-test backend task creation for Standard Artifact outputs with no explicit `project_id`.
- Unit-test backend rejection of existing ArtifactVersion bindings without project context.
- Regression-test tool detail page no longer blocks no-project uploaded Standard inputs.
- Regression-test workflow Fetch PDB -> LVpocket auto-binds via Artifact Slots and does not require manual field mapping.
- Regression-test saved workflows hydrate stale nodes from current contracts before preflight.

## Migration Strategy

Keep legacy behavior working while moving new tools to the stricter model:

1. Treat `agent_capability` as compatibility metadata.
2. Derive workflow capability from `artifacts` when `agent_capability` is absent.
3. Keep existing schema file inputs functional as upload fallback.
4. Move duplicated frontend binding code into a shared domain module.
5. Move backend private binding helpers behind a single task-preparation module.

The first implementation should not change database structure. It should clarify interfaces, remove the frontend hard block, and make the backend task-preparation path the authority.
