# Editable Workflow Canvas Design

## Goal

Turn the current template graph into a usable lightweight workflow editor: users can add real tools as nodes, delete editable nodes, create simple upstream edges, save/load edited graphs, and run ready nodes.

## Scope

- Keep the current template as the initial workflow.
- Store edited nodes and edges in the workflow Pinia store.
- Use existing tool APIs and stores; do not add a new backend scheduler.
- Keep execution on the existing task creation flow.
- Do not implement mouse-drag line drawing yet; use inspector controls for edges.

## UI Model

The workflow page continues to use three panes: node list, canvas, and inspector. The canvas toolbar gets an "Add tool node" selector that lists currently available tools. Tool nodes get a delete control; input/result template nodes remain protected.

The inspector shows real tool options from `toolsStore.workbenchGroups` and `toolsStore.workflowToolOptions`, not only template slug placeholders. For a selected editable tool node, the inspector can add an upstream edge by choosing a source node and semantic artifact type.

## State Model

`useWorkflowStore` owns:

- `canvasNodes`
- `canvasEdges`
- `addToolNode`
- `deleteCanvasNode`
- `addCanvasEdge`
- `deleteCanvasEdge`
- `ensureCanvasFromTemplate`

Deleting a node removes connected edges, position overrides, selected tools, node tasks, and artifact bindings.

## Persistence

Save payloads use edited `canvasNodes` and `canvasEdges`. Loading a workflow replaces the editable graph and restores selected tools and positions.

## Validation

Frontend tests cover tool listing in the inspector, add/delete node state cleanup, edge creation, page wiring, save payload source, and production build.
