# Repository Guidelines

## Project Structure & Module Organization

This repository is a scientific computing tool platform with a FastAPI backend and Vue 3 frontend. Backend source lives in `backend/app/`, with API routes in `backend/app/api/v1/`, ORM models in `backend/app/models/`, schemas in `backend/app/schemas/`, services in `backend/app/services/`, storage/cache adapters in `backend/app/storage/` and `backend/app/cache/`, and Celery code in `backend/app/worker/`. Frontend source lives in `frontend/src/`, organized by `api/`, `components/`, `views`, `stores`, `router`, `types`, and `utils`. Tests are in `test/`. Tool examples and sample inputs are in `example/`. Design, SQL, and implementation notes are under `docs/`.

## Build, Test, and Development Commands

- `./start-dev.sh`: starts the backend on `8000` and the frontend on `8585` with hot reload.
- `cd backend && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload`: run the API server.
- `cd frontend && npm run dev -- --host 0.0.0.0 --port 8585`: run only the Vite frontend.
- `cd frontend && npm run build`: type-check and build the frontend.
- `pytest test`: run the Python test suite from the repository root.
- `./start-celery.sh`: start Redis, Celery worker, and Flower via `docker-compose.celery.yml`.

## Workspace Convention

Do active development on branch `6.16` in `/data/zhouyc/cpumodel_sciminer`. Avoid side worktrees unless the task explicitly requires isolation, and keep runtime artifacts out of Git.


## Coding Style & Naming Conventions

Use Python 3.10+ and keep backend modules small and service-oriented. Prefer `snake_case` for Python files, functions, and variables, and `PascalCase` for Pydantic and ORM classes. Vue components should use `PascalCase.vue`; composables should use `useXxx.ts`. Frontend formatting follows `frontend/.prettierrc`: 2 spaces, single quotes, no semicolons, 100-character line width, LF endings. ESLint allows Vue single-word component names and warns on explicit `any`.

## Testing Guidelines

Backend tests use `pytest` and `pytest-asyncio`. Name new tests `test_*.py` and place them in `test/`, matching the feature area when possible, such as `test_model_services_api.py` or `test_file_artifacts_api.py`. Add regression tests for API behavior, task execution, file handling, agent workflows, and security-sensitive changes. Run focused tests first, then `pytest test` before handing off.

## Commit & Pull Request Guidelines

Recent history follows Conventional Commit-style messages, for example `feat: add AIDD agent workflow support` and `style(frontend): center workflow page header`. Use short imperative summaries with an optional scope: `feat(frontend): ...`, `fix(api): ...`, `test: ...`. Pull requests should include a concise description, affected areas, linked issues when available, test results, and screenshots or recordings for UI changes.

## Security & Configuration Tips

Do not commit real secrets, access keys, generated uploads, or local databases. Use `backend/.env.example` as the template for local configuration, and change `JWT_SECRET_KEY` and production service credentials outside version control.
