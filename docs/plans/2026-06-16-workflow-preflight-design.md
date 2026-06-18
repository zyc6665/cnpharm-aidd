# Workflow Preflight Design

## Goal

Add a workflow-level preflight check so researchers can see whether a graph can run before starting automated execution.

## Approach

Keep the feature frontend-only for this stage. A pure helper in `frontend/src/workflow/preflight.ts` converts the current template, node statuses, and ready node ids into a compact summary. The Vue page renders that summary before the canvas with runnable counts, blocked counts, issue details, and a direct run action.

## User Experience

The panel appears between the save/load toolbar and the canvas. It answers three questions quickly:

- How many nodes can run now?
- Which nodes are blocked, failed, running, or missing a tool?
- What should the user inspect before launching?

Each issue links back to the relevant node by selecting it in the existing inspector.

## Data Flow

`index.vue` already computes `nodeStatuses` and `readyToolNodeIds`. The new `workflowPreflight` computed value passes those into `buildWorkflowPreflight`. The panel emits `run-ready-nodes` to reuse the existing execution path and `select-node` to reuse existing node selection.

## Testing

Use Node tests for the pure helper and source-level surface tests for page integration. Build verification remains `npm run build`.
