# Workflow Dark Surface Cleanup Design

## Context

Checklist item 2.3.7 originally identified hard-coded translucent white backgrounds in the
workflow inspector and preflight panel. Those parent components now use semantic theme surfaces,
but two backgrounds moved into inspector child components during the inspector split:

- `WorkflowNodeRunPanel.vue` uses a translucent white run summary.
- `WorkflowNodeStatusBadge.vue` uses a translucent white badge surface.

## Decision

Replace both hard-coded white backgrounds with the existing `@bg-elevated` token. This token
already maps to dark and light CSS custom properties, preserves visual separation from the parent
surface, and avoids expanding the global theme API for two small elements.

Status-specific red, amber, blue, and green colors remain unchanged. They communicate state and
are not neutral surface backgrounds.

## Alternatives

- `@bg-surface`: theme-aware, but does not distinguish nested content from the parent surface.
- A new translucent surface token: preserves transparency, but adds unnecessary global theme
  complexity for this narrow cleanup.
- `@bg-elevated`: reuses the current design system and keeps the change local.

## Verification

- Extend the workflow inspector surface test to reject hard-coded translucent white backgrounds
  across the inspector and its split child components.
- Assert that the run summary and status badge use `@bg-elevated`.
- Run focused workflow tests, the full frontend test suite, and the production frontend build.
