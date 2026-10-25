# Tool Contract Unification Design

## Goal

Create one backend contract for platform tools so Agent, workflow, and frontend code stop maintaining separate field mappings.

## Scope

This phase does not change the database or remove existing API fields. It adds a normalized `ToolContract` serializer and moves AIDD Agent tool summaries to derive from that contract.

## Contract Shape

`ToolContract` contains a version marker, stable identity fields, executor metadata, input/output schemas, and optional Agent capability metadata:

- `contract_version`
- `id`, `slug`, `name`, `description`, `status`
- `executor.type`, `executor.timeout_sec`
- `schema.input`, `schema.output`
- `capability.enabled`, `stage`, `inputs`, `outputs`, `defaults`, `virtual`

Agent compatibility keeps `tool_slug` in its public summary during this phase, but the source of truth becomes `slug`.

## Data Flow

Platform tools are normalized by `build_tool_contract(tool)`. Static virtual Agent tools are normalized by `build_virtual_tool_contract(capability)`. `load_available_tool_summaries` converts contracts into the existing planner-facing summary shape, so planner behavior remains stable while the mapping logic is centralized.

## Testing

Tool import validation rejects enabled Agent capabilities whose input fields do not exist in `input_schema`, whose semantic types are unknown, or whose defaults point at missing schema fields. This shifts failures from Agent runtime to tool onboarding.

Add unit tests for contract serialization, Agent summary compatibility, planner `slug` compatibility, and import-time capability validation. Run focused AIDD registry tests and existing Agent tests before handoff.
