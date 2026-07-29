# Backend Unused Imports Cleanup Plan

**Goal:** Remove unused imports from tracked backend source and prevent new `F401` violations.

**Scope:** `backend/app`, backend development dependencies, CI, and focused regression tests.
Generated local files and development data are explicitly out of scope.

## Task 1: Record the failing quality baseline

1. Run `python -m flake8 backend/app --select F401`.
2. Confirm each finding is an internal unused import rather than a public re-export.

## Task 2: Clean tracked backend imports

1. Remove only imports reported by `F401`.
2. Re-run the focused check until it passes.
3. Run focused tests covering agent planning, workflows, executors, workers, auth, files, GPU,
   logging, monitoring, schemas, email, and WebSocket behavior.

## Task 3: Make the check reproducible

1. Pin Flake8 in `backend/requirements-dev.txt`.
2. Install backend development requirements in CI.
3. Add a backend lint step using the exact focused command.
4. Run CI contract tests and the full backend test suite.

