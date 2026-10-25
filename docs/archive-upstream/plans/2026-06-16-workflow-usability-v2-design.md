# Workflow Usability V2 Design

## Goal

Make the workflow page easier to use as a daily team workbench by separating graph editing, node configuration, dependency management, and execution feedback.

## Current Gaps

- The tool library lives inside the canvas area and consumes graph space.
- The inspector is a long mixed panel: tool selection, dependency editing, input summary, task result, and execution form compete for attention.
- Run readiness is only represented by node badges, so users cannot quickly see why the workflow is blocked.
- Top-level actions still use mixed English labels.

## Design

Use a three-column operational layout:

- Left sidebar: template selector, run summary, node list, searchable tool library.
- Center canvas: graph only, with node/edge rendering and drag interactions.
- Right inspector: tabbed detail panel with `配置`, `依赖`, and `结果`.

The top action bar remains responsible for workflow name, save/load, and one-click execution. The run summary shows counts for ready, blocked, running, completed, and failed nodes. Each node row also shows a short reason such as `缺少输入`, `等待上游`, or `可运行`.

## Data Flow

The existing Pinia workflow store remains the source of truth for nodes, edges, selected tools, drafts, task refs, and canvas positions. The page computes status counts and display reasons from `nodeStatuses`, `taskByNode`, selected tools, and required inputs. The inspector emits the same edge/tool/task events as before, but presents them inside tabs.

## Testing

Add source-level regression tests for:

- Workflow page exposes a sidebar tool library and run summary.
- Canvas no longer owns the tool library.
- Inspector exposes tabbed `配置` / `依赖` / `结果` sections.
- Existing run/save/load/graph tests continue to pass.
