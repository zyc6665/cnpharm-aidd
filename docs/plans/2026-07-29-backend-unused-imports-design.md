# Backend Unused Imports Cleanup Design

## Context

Checklist item 3.2 reports unused Python imports and generated `.pyc` files. Local generated
files are required for development and testing, so this change addresses only unused imports in
Git-tracked backend source.

## Decision

- Use Flake8's `F401` rule as the narrow, reproducible definition of an unused import.
- Remove confirmed unused imports from `backend/app` without reformatting surrounding code.
- Pin Flake8 in `backend/requirements-dev.txt` and run the same focused check in CI.
- Preserve local `.pyc`, caches, databases, uploads, and other development data.

## Alternatives

- One-time cleanup: smaller diff, but allows the same debt to return.
- Enable all Flake8 rules: stronger enforcement, but creates unrelated formatting and style work.
- Focused `F401` gate: fixes the diagnosed debt and prevents recurrence with limited blast radius.

## Verification

- `python -m flake8 backend/app --select F401`
- Focused backend tests for modules touched by the cleanup.
- Full `python -m pytest test/` regression suite.

