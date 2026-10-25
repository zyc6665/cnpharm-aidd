# Core Tool and Workflow UX Design

## Goal

Make standalone tool runs and workflow runs predictable, let project workflows start from project artifacts or new files, and ensure every accepted parameter schema can be edited in the runtime form.

## Decisions

- A node-level run remains an independent Task for trying one tool. A WorkflowRun remains a new full workflow execution; node-level Tasks are not silently treated as completed nodes in a new run.
- Canvas node actions focus the node's configuration. Users run a node from its parameter form, and start a full WorkflowRun from the workflow-level action.
- Project workflows list compatible Typed Artifacts from their current project and can upload an input into that project. A workflow input keeps the selected ArtifactVersion reference; the backend validates its project, lifecycle, and semantic type before preparing the node input.
- Existing Task output files remain selectable in non-project workflows. Direct uploads there remain normal file inputs.
- Runtime parameter forms support the JSON Schema types accepted by registration: object and general array values use JSON text input; string email and URL formats use appropriate text inputs.
- Condition and Map nodes expose their execution fields in the inspector. Condition branches are stored on edges and preserved when loading and saving definitions.
- Changing the canvas preset, starting a new workflow, or loading another definition asks before discarding unsaved edits.

## Data Flow

Tool parameter values and Artifact inputs continue through Run Preparation. Workflow project ArtifactVersion references are validated against the workflow project's membership and materialized through the same node preparation path. A standalone node Task remains separate from WorkflowRun state and is labeled accordingly in the UI.

## Scope

No database migration is planned. Existing workflow and Task records remain readable. This change does not alter the executor model or introduce partial WorkflowRun continuation.

## Verification

Use frontend production build, backend compilation, and `git diff --check`. Do not add or run test suites in this task.
