# Drug Discovery Tool Templates Backend Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add backend infrastructure for static drug-discovery tool templates that generate existing Tool import configs.

**Architecture:** Keep templates as versioned YAML files under `backend/app/tool_templates/drug_discovery/`. Validate them with Pydantic and convert them into the existing `ToolVersion.config` shape without adding database tables or executor variants.

**Tech Stack:** FastAPI backend, Pydantic v2, PyYAML, existing `ToolContract` and tool import validation services.

---

### Task 1: Template Schema And Loader

**Files:**
- Create: `backend/app/tool_templates/schemas.py`
- Create: `backend/app/tool_templates/loader.py`
- Create: `backend/app/tool_templates/__init__.py`
- Test: `test/test_drug_discovery_tool_templates.py`

**Steps:**
1. Write failing tests for loading bundled templates, enforcing `aidd.sciminer/result.v2`, and generating existing tool import configs.
2. Add Pydantic models for metadata, capability, resource profile, expected outputs, and smoke tests.
3. Add YAML loader functions for one template and all templates in a family.
4. Add `build_tool_import_config_from_template()` to produce current `platform_tool.json` shape.
5. Run focused backend tests.

### Task 2: Bundled Drug Discovery Templates

**Files:**
- Create: `backend/app/tool_templates/drug_discovery/*.yaml`
- Test: `test/test_drug_discovery_tool_templates.py`

**Steps:**
1. Add templates for RDKit properties, SA score, conformer generation, Open Babel conversion, ligand preparation, Vina, Smina, rescoring, interaction summary, ADMET API, toxicity API, and GROMACS MD placeholder.
2. Use standard artifact refs where possible: `protein_structure@1`, `ligand_structure@1`, `molecule_table@1`, `run_report@1`.
3. Include `resource_profile`, `sample_inputs`, and `smoke_test` in every template.
4. Run focused backend tests and diff checks.
