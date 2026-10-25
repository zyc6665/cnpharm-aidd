# Workflow Results Report Design

## Goal

Turn the workflow page into a results-first research workspace that helps a drug discovery user review outputs, judge whether a run is trustworthy, and export a concise report for the team.

## Current Gaps

- Result content is scattered across task detail, result panels, and file downloads.
- The page does not summarize what the workflow produced, which nodes succeeded, or which outputs are worth carrying forward.
- There is no single place to copy a run summary into a lab note or team discussion.

## Design

Add a workflow-level results panel tied to the existing workflow state and task history. The panel should summarize the current run in three layers:

- workflow summary: template name, run status, completed nodes, failed nodes, and last updated time
- artifact summary: key outputs per node, top-ranked files, and direct download links
- decision summary: a short textual note for downstream users, such as `可进入 ADMET` or `需重新检查 docking`

Expose a lightweight report export action that generates Markdown on the client. The report should include the workflow name, selected tools, node status table, file links, and a short execution timeline. This keeps the feature usable without backend changes.

## Data Flow

The report view reads from the existing workflow store, task store, artifacts store, and result panels. It derives a stable summary from current node tasks and file outputs, then renders it in a dedicated results area. Export uses the same computed summary to create a downloadable `.md` file.

## Testing

Add regression tests for:

- workflow page exposes a results summary panel and report export action
- report generation includes workflow name, node status rows, and artifact links
- result summary prefers real task/output data over empty placeholders
- existing workflow run and canvas tests still pass
