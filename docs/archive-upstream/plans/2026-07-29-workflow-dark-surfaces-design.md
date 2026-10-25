# Workflow Dark Surface Cleanup Design

## Context

Checklist item 2.3.7 originally identified hard-coded translucent white backgrounds in the
workflow inspector and preflight panel. Those parent components now use semantic theme surfaces,
but a directory-wide audit found the same light-only styling in older workflow panels and in
components extracted from the inspector. The remaining debt includes neutral white or near-white
backgrounds, borders, and an SVG label halo across the workflow component directory.

## Decision

Use the existing runtime theme tokens according to surface hierarchy:

- Top-level workflow panels use `@bg-surface` and `@border-color-hover`.
- Nested cards, list items, tool summaries, and badges use `@bg-elevated` and `@border-color`.
- Interactive selected and hover states keep using `@accent-color-light`.
- The workflow edge label halo uses `@bg-surface` so it matches the canvas.

These tokens already map to dark and light CSS custom properties and avoid expanding the global
theme API.

Status-specific red, amber, blue, and green colors remain unchanged. They communicate state and
are not neutral surface backgrounds.

## Alternatives

- Replace only the two inspector descendants: leaves the same defect throughout the workflow.
- Add translucent surface and border tokens: preserves the old appearance more closely, but adds
  unnecessary global theme complexity.
- Reuse the existing surface hierarchy: removes the light-only subsystem and keeps the theme API
  unchanged.

## Verification

- Extend the inspector surface test for the split child components.
- Add a directory-level regression test that rejects the audited neutral light-only color values
  in every workflow Vue component.
- Assert representative top-level and nested components use the correct semantic tokens.
- Run focused workflow tests, the full frontend test suite, and the production frontend build.
