# Platform Architecture and Workflow Usability Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Upgrade the platform from single-tool execution to a contract-driven drug discovery workflow system that is maintainable for team development and usable by pharmaceutical researchers.

**Architecture:** Make `ToolContract` the shared boundary for backend APIs, Agent planning, workflow orchestration, and frontend rendering. Workflow nodes, semantic artifacts, tool input mapping, and output extraction should be derived from contracts instead of duplicated static mappings.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic, pytest, Vue 3, Pinia, TypeScript, Ant Design Vue, Vite.

---

## Scope

This roadmap coordinates three existing work streams:

- Tool contract unification: `docs/plans/2026-06-17-tool-contract-unification.md`
- Workflow usability MVP: `docs/plans/2026-06-16-workflow-usability-mvp.md`
- Canvas workflow evolution: `docs/plans/2026-06-15-template-workflow-canvas.md`

Do not start with a frontend rewrite. First remove contract and semantic drift, then improve workflow usability, then add free-form canvas orchestration.

## Phase 0: Repository Hygiene and Baseline

**Target window:** Day 1

**Files:**
- Modify: `.gitignore`
- Review: `git status --short`
- Test: existing focused tests in `test/`

**Tasks:**
1. Audit dirty runtime artifacts: `__pycache__/`, SQLite files, uploads, logs, local images, backup databases.
2. Add or verify ignore rules for generated files and local runtime storage.
3. Restore or replace missing example fixtures used by `test/test_tool_import_config.py`.
4. Run focused baseline tests:
   - `pytest test/test_tool_import_config.py -q`
   - `pytest test/test_tool_contracts.py -q`
   - `pytest test/test_aidd_agent_registry.py test/test_aidd_agent_planner.py -q`

**Acceptance criteria:**
- Generated runtime files do not appear in normal `git status`.
- Import-config tests no longer require missing repository files.
- The team has a clean baseline before feature changes.

## Phase 1: Make ToolContract the Platform Boundary

**Target window:** Days 2-5

**Files:**
- Modify: `backend/app/services/tool_contracts.py`
- Modify: `backend/app/api/v1/tools.py`
- Modify: `backend/app/schemas/tools.py`
- Test: `test/test_tool_contracts.py`
- Test: `test/test_tool_import_config.py`

**Tasks:**
1. Add a typed contract response schema for `ToolContract`.
2. Add `GET /api/v1/tools/{tool_id}/contract`.
3. Include contract summaries in `/api/v1/tools/workbench-groups`.
4. Add contract validation status and validation errors to contract output.
5. Enforce contract validation when importing, editing, or publishing tools.
6. Add snapshot-style API tests for tool detail and workbench group contract payloads.

**Acceptance criteria:**
- Frontend and Agent can fetch the same contract shape.
- A tool with invalid `agent_capability` cannot be published silently.
- Contract output includes input schema, output schema, executor, capability inputs, capability outputs, defaults, and version.

## Phase 2: Unify Semantic Types

**Target window:** Days 4-7

**Files:**
- Create: `backend/app/services/semantic_types.py`
- Modify: `backend/app/agents/aidd/capabilities.py`
- Modify: `tool_import_config.py`
- Modify: `frontend/src/workflow/artifact-types.ts`
- Modify: `frontend/src/workflow/tool-bindings.ts`
- Test: `test/test_aidd_agent_capabilities.py`
- Test: `test/test_tool_import_config.py`

**Tasks:**
1. Define canonical semantic types in one backend module:
   - `protein_pdb`
   - `pocket_pdb`
   - `generated_ligand`
   - `ligand_pdb`
   - `smiles_csv`
   - `ranking_csv`
   - `docking_pose`
   - `docking_report`
   - `affinity_report`
   - `property_report`
   - `optimized_lead`
2. Replace duplicated backend semantic-type sets with the shared module.
3. Add a temporary alias layer only for migration from frontend names:
   - `protein_structure -> protein_pdb`
   - `pocket_structure -> pocket_pdb`
4. Update frontend workflow artifact types to canonical names.
5. Add regression tests proving Agent and workflow use the same semantic values.

**Acceptance criteria:**
- New code uses only canonical semantic types.
- Existing saved artifacts can still be read through migration aliases.
- There is one source of truth for supported semantic types.

## Phase 3: Contract-Driven Workflow Workbench

**Target window:** Week 2

**Files:**
- Modify: `frontend/src/types/models.d.ts`
- Modify: `frontend/src/api/tools.ts`
- Modify: `frontend/src/stores/tools.ts`
- Modify: `frontend/src/workflow/artifact-resolver.ts`
- Modify: `frontend/src/components/workflow/WorkflowRunPanel.vue`
- Modify: `frontend/src/components/workflow/WorkflowArtifactPanel.vue`
- Test: add focused frontend unit tests if available
- Test: `cd frontend && npm run build`

**Tasks:**
1. Add TypeScript types for `ToolContract`, `ToolCapabilityInput`, and `ToolCapabilityOutput`.
2. Fetch workbench groups with embedded contract summaries.
3. Replace static field binding lookup with contract-derived input bindings.
4. Replace static output extractors with contract-derived output extraction rules.
5. Add a preflight panel showing missing inputs, matched artifacts, invalid formats, and expected outputs.
6. Keep static `tool-bindings.ts` only as a compatibility fallback during migration.

**Acceptance criteria:**
- A newly imported contract-valid tool appears in the workbench without frontend code changes.
- Running a downstream tool can auto-fill inputs from upstream artifacts by semantic type.
- Users see clear preflight errors before submitting a task.

## Phase 4: Agent and LangGraph Contract Alignment

**Target window:** Week 2-3

**Files:**
- Modify: `backend/app/agents/aidd/registry.py`
- Modify: `backend/app/agents/aidd/graph_nodes.py`
- Modify: `backend/app/agents/aidd/plan_schema.py`
- Modify: `backend/app/agents/aidd/service.py`
- Test: `test/test_aidd_langgraph_nodes.py`
- Test: `test/test_aidd_agent_registry.py`
- Test: `test/test_aidd_agent_reconcile.py`

**Tasks:**
1. Route LangGraph tool discovery through the same contract summary path as the Agent service.
2. Prefer `slug` internally while keeping `tool_slug` as an API compatibility alias.
3. Store planning traces with selected contract version and semantic input mapping.
4. Improve failure messages when required semantic outputs are missing.
5. Add tests for dynamic platform tools in LangGraph discovery.

**Acceptance criteria:**
- Agent service and LangGraph see the same available tools.
- Dynamic tools are not excluded because they are absent from static capability tables.
- Agent failures identify the missing semantic type, expected output rule, and source task.

## Phase 5: Workflow Persistence and One-Click Run

**Target window:** Week 3-4

**Files:**
- Create or modify backend workflow models and migrations
- Create or modify workflow API routes
- Modify: `frontend/src/stores/workflow.ts`
- Modify workflow canvas/workbench components
- Test: backend API tests for workflow templates and runs

**Tasks:**
1. Add `WorkflowTemplate` for reusable workflow definitions.
2. Add `WorkflowRun` for one execution instance.
3. Store nodes, edges, tool IDs, tool slugs, tool versions, params, and semantic mappings.
4. Add save, load, duplicate, and delete workflow APIs.
5. Add one-click execution with topological ordering and preflight validation.
6. Persist each node result and artifact lineage.

**Acceptance criteria:**
- Users can save a workflow and rerun it with a new input file.
- One-click run stops before execution if required inputs are missing.
- A workflow run records the exact tool versions and params used.

## Phase 6: Free-Drag Canvas and Researcher UX

**Target window:** Week 4-5

**Files:**
- Modify canvas workflow components
- Modify workflow inspector and run panel components
- Test: `cd frontend && npm run build`
- Optional: Playwright smoke test for `/workflow`

**Tasks:**
1. Add tool palette filtering by stage, semantic input, semantic output, and executor.
2. Allow node add, delete, duplicate, drag, connect, disconnect, and disable.
3. Validate edges by semantic compatibility.
4. Add node-level status, logs, input source, output artifacts, and rerun action.
5. Add templates for common AIDD flows:
   - protein PDB to pocket prediction to molecule generation
   - pocket PDB to molecule generation to ADMET
   - protein PDB and ligand to docking and affinity prediction
6. Add Agent-assisted workflow draft generation after the contract path is stable.

**Acceptance criteria:**
- Users can build and run a valid workflow without editing JSON.
- Invalid node connections are blocked with a clear reason.
- A researcher can inspect each node's input, output, status, and next recommended action.

## Phase 7: Team Development Standards

**Target window:** Parallel with all phases

**Files:**
- Modify: `AGENTS.md`
- Create or update: `docs/tool-contract-guide.md`
- Create or update: `docs/team-development-workflow.md`
- Add tests as features land

**Tasks:**
1. Document the tool onboarding process.
2. Document supported semantic types and examples.
3. Document contract validation rules.
4. Document frontend workflow rules and API expectations.
5. Add PR checklist:
   - tests run
   - contract changes documented
   - screenshots for UI changes
   - no runtime artifacts committed

**Acceptance criteria:**
- New contributors can add a contract-valid tool using the guide.
- Reviewers have a clear checklist for tool, Agent, and workflow changes.

## Milestone Schedule

| Milestone | Window | Outcome |
| --- | --- | --- |
| M0 | Day 1 | Clean repository baseline and reliable focused tests |
| M1 | Days 2-5 | ToolContract exposed and enforced by backend |
| M2 | Days 4-7 | Semantic types unified across Agent and workflow |
| M3 | Week 2 | Workbench uses contract-derived input/output rules |
| M4 | Week 2-3 | Agent and LangGraph use the same contract source |
| M5 | Week 3-4 | Workflow save/load and one-click run |
| M6 | Week 4-5 | Free-drag canvas with compatibility validation |
| M7 | Ongoing | Team documentation and PR standards |

## Testing Strategy

Run focused tests after each phase, then broaden:

```bash
pytest test/test_tool_contracts.py test/test_tool_import_config.py -q
pytest test/test_aidd_agent_registry.py test/test_aidd_agent_planner.py test/test_aidd_langgraph_nodes.py -q
pytest test/test_aidd_agent_reconcile.py -q
cd frontend && npm run build
```

For UI-heavy phases, add a smoke test for `/workflow` that verifies:

- workbench groups load
- at least one tool node/card renders
- preflight panel renders
- no console render error blocks the route

## Risks and Controls

- **Risk:** Keeping both old and new semantic names creates hidden bugs.  
  **Control:** Keep aliases only at import/read boundaries; all new internal state uses canonical names.

- **Risk:** Frontend static bindings continue to diverge from backend contracts.  
  **Control:** Mark static bindings as compatibility fallback and add tests for contract-driven tools.

- **Risk:** Existing saved tasks or artifacts break after semantic migration.  
  **Control:** Add read-time migration aliases and do not rewrite historical records until a separate migration is planned.

- **Risk:** One-click run launches expensive jobs with invalid inputs.  
  **Control:** Require preflight validation before workflow execution.

- **Risk:** Team commits local runtime data.  
  **Control:** Enforce `.gitignore`, clean baseline, and PR checklist.

## Recommended Execution Order

Start with Phase 0, Phase 1, and Phase 2. Do not begin broad canvas work until the contract and semantic layers are stable. Canvas UX should consume contract data, not define tool behavior itself.
