# Tool Examples Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add one-click runnable examples for tools, including predefined parameters, registered example input files, and file preview.

**Architecture:** Store examples in `ToolVersion.config`, compatible with existing `example_params` and new `examples` arrays. Backend tool APIs resolve, validate, preview, and apply example files; the Vue tool detail page fetches example metadata, fills form state, binds example files, and previews text files.

**Tech Stack:** FastAPI, SQLAlchemy async, local file storage, Vue 3, Ant Design Vue, Pinia, TypeScript, pytest, vue-tsc/Vite.

---

### Task 1: Backend Example Schemas

**Files:**
- Modify: `backend/app/schemas/tools.py`

**Step 1: Write the failing test**

Add assertions in `test/test_tool_import_config.py` or a new API test later that expects `/tools/{tool_id}/example` to return:

```python
{
    "name": "默认示例",
    "params": {...},
    "input_files": [
        {
            "field": "protein_pdb",
            "path": "input/protein.pdb",
            "filename": "protein.pdb",
            "exists": True,
            "previewable": True
        }
    ]
}
```

**Step 2: Add schemas**

Add Pydantic models:

```python
class ToolExampleFileResponse(BaseModel):
    field: str
    path: str
    filename: str
    size_bytes: Optional[int] = None
    content_type: Optional[str] = None
    exists: bool = False
    previewable: bool = False


class ToolExampleResponse(BaseModel):
    name: str
    description: Optional[str] = None
    params: Dict[str, Any] = Field(default_factory=dict)
    input_files: List[ToolExampleFileResponse] = Field(default_factory=list)


class ToolExampleApplyResponse(BaseModel):
    params: Dict[str, Any] = Field(default_factory=dict)
    files: Dict[str, FileUploadResponse] = Field(default_factory=dict)


class ToolExampleFilePreviewResponse(BaseModel):
    field: str
    filename: str
    content_type: Optional[str] = None
    content: Optional[str] = None
    truncated: bool = False
    previewable: bool = False
```

**Step 3: Run focused backend type/import check**

Run: `PYTHONPATH=backend pytest test/test_tool_import_config.py -q`

Expected: existing tests still pass.

### Task 2: Backend Example Resolver

**Files:**
- Modify: `backend/app/api/v1/tools.py`
- Test: `test/test_tool_examples_api.py`

**Step 1: Write failing tests**

Create tests for:

- default example from `config["examples"][0]`
- fallback example from `config["example_params"]`
- path traversal rejected for `../secret.txt`
- missing example returns no data or 404-style validation response

**Step 2: Implement resolver helpers**

Add helpers near existing serializer functions:

```python
TEXT_PREVIEW_EXTENSIONS = {".txt", ".json", ".csv", ".fasta", ".fa", ".pdb", ".log", ".md"}
EXAMPLE_PREVIEW_MAX_BYTES = 64 * 1024


def get_default_tool_example(config: dict) -> Optional[dict]:
    examples = config.get("examples")
    if isinstance(examples, list) and examples:
        first = examples[0]
        if isinstance(first, dict):
            return {
                "name": str(first.get("name") or "默认示例"),
                "description": first.get("description"),
                "params": first.get("params") or {},
                "input_files": first.get("input_files") or {},
            }

    example_params = config.get("example_params")
    if isinstance(example_params, dict):
        if "params" in example_params or "input_files" in example_params:
            params = dict(example_params.get("params") or {})
            for key, value in example_params.items():
                if key not in {"params", "input_files", "task_name"}:
                    params[key] = value
            if "task_name" in example_params:
                params["task_name"] = example_params["task_name"]
            return {
                "name": "默认示例",
                "description": None,
                "params": params,
                "input_files": example_params.get("input_files") or {},
            }

        return {
            "name": "默认示例",
            "description": None,
            "params": example_params,
            "input_files": {},
        }

    return None
```

Resolve file paths under `PROJECT_ROOT / "example" / tool.slug` by default, with optional `config["example_base_dir"]`. Use `.resolve()` and verify the resolved path is inside the base directory.

**Step 3: Run failing tests**

Run: `PYTHONPATH=backend pytest test/test_tool_examples_api.py -q`

Expected before implementation: fail on missing endpoint.

**Step 4: Add endpoints**

Add before `@router.get("/{tool_id}")` so static routes are not swallowed:

- `GET /{tool_id}/example`
- `POST /{tool_id}/example/apply`
- `GET /{tool_id}/example/files/{field}/preview`

For apply, create `FileModel` rows with `source_type=FileSourceType.UPLOAD`, `owner_id=current_user.id`, `is_public=False`, copy content to `get_file_path(file_record.id, filename)`, and return `FileUploadResponse`.

**Step 5: Run tests**

Run: `PYTHONPATH=backend pytest test/test_tool_examples_api.py -q`

Expected: pass.

### Task 3: Frontend API Types

**Files:**
- Modify: `frontend/src/types/models.d.ts`
- Modify: `frontend/src/api/tools.ts`

**Step 1: Add TypeScript types**

Add:

```ts
export interface ToolExampleFile {
  field: string
  path: string
  filename: string
  size_bytes?: number
  content_type?: string
  exists: boolean
  previewable: boolean
}

export interface ToolExample {
  name: string
  description?: string
  params: Record<string, unknown>
  input_files: ToolExampleFile[]
}

export interface ToolExampleApplyResult {
  params: Record<string, unknown>
  files: Record<string, FileUploadResponse>
}

export interface ToolExampleFilePreview {
  field: string
  filename: string
  content_type?: string
  content?: string
  truncated: boolean
  previewable: boolean
}
```

**Step 2: Add API functions**

In `frontend/src/api/tools.ts`:

```ts
export const getToolExample = (id: string): Promise<ApiResponse<ToolExample | null>> =>
  get<ToolExample | null>(`/tools/${id}/example`)

export const applyToolExample = (id: string): Promise<ApiResponse<ToolExampleApplyResult>> =>
  post<ToolExampleApplyResult>(`/tools/${id}/example/apply`)

export const previewToolExampleFile = (id: string, field: string): Promise<ApiResponse<ToolExampleFilePreview>> =>
  get<ToolExampleFilePreview>(`/tools/${id}/example/files/${encodeURIComponent(field)}/preview`)
```

**Step 3: Run frontend type check**

Run: `cd frontend && npm run build`

Expected before UI changes: may pass after imports are unused-safe or fail only on missing imports.

### Task 4: Frontend Form Fill Helpers

**Files:**
- Modify: `frontend/src/views/tools/detail-schema.ts`

**Step 1: Add helper tests if frontend test harness exists**

Search current frontend tests. If no frontend unit test setup exists, keep helper pure and verify through `npm run build`.

**Step 2: Add helper**

Add:

```ts
export function flattenExampleParams(
  flattenedSchema: ToolSchema,
  exampleParams: Record<string, unknown>
): Record<string, unknown> {
  const values: Record<string, unknown> = {}
  for (const [key, prop] of Object.entries(flattenedSchema.properties)) {
    if (prop._parentKey && prop._originalKey) {
      const parent = exampleParams[prop._parentKey]
      if (parent && typeof parent === 'object' && !Array.isArray(parent)) {
        const nested = parent as Record<string, unknown>
        if (Object.prototype.hasOwnProperty.call(nested, prop._originalKey)) {
          values[key] = nested[prop._originalKey]
        }
      }
      continue
    }
    if (Object.prototype.hasOwnProperty.call(exampleParams, key)) {
      values[key] = exampleParams[key]
    }
  }
  return values
}
```

**Step 3: Run build**

Run: `cd frontend && npm run build`

Expected: pass after UI imports are wired.

### Task 5: Frontend Tool Detail UI

**Files:**
- Modify: `frontend/src/views/tools/Detail.vue`
- Modify: `frontend/src/locales/zh-CN/index.ts`
- Modify: `frontend/src/locales/en-US/index.ts`

**Step 1: Add state and API calls**

Add refs:

```ts
const example = ref<ToolExample | null>(null)
const exampleLoading = ref(false)
const applyingExample = ref(false)
const previewOpen = ref(false)
const previewLoading = ref(false)
const preview = ref<ToolExampleFilePreview | null>(null)
```

After `fetchToolDetail`, call `fetchToolExample(id)`.

**Step 2: Add actions**

`handleUseExample`:

- if not logged in, warn and route to `/login`
- call apply endpoint
- flatten returned params
- write non-file values into `formState`
- bind returned files into `selectedArtifacts`-compatible objects or add a small `exampleFiles` map that `handleSubmit` understands

Recommended minimal path: extend `UploadedToolFile` construction in `handleSubmit` to include an `exampleUploadedFiles` map, avoiding fake `ArtifactFile`.

**Step 3: Add preview modal**

Use Ant Design Vue modal and textarea/pre:

- Show filename and truncated state.
- Disable preview button when `exists=false` or `previewable=false`.

**Step 4: Add template**

Place above `<a-form>`:

```vue
<div v-if="example" class="tool-example-panel">
  <div>
    <h3>{{ example.name }}</h3>
    <p v-if="example.description">{{ example.description }}</p>
  </div>
  <a-space wrap>
    <a-button :loading="applyingExample" @click="handleUseExample">
      <ThunderboltOutlined />
      {{ t('tools.useExample') }}
    </a-button>
  </a-space>
  <div v-if="example.input_files.length" class="example-files">
    ...
  </div>
</div>
```

**Step 5: Run build**

Run: `cd frontend && npm run build`

Expected: pass.

### Task 6: End-to-End Verification

**Files:**
- No direct file changes unless tests reveal a bug.

**Step 1: Run backend focused tests**

Run:

```bash
PYTHONPATH=backend pytest test/test_tool_examples_api.py test/test_tool_import_config.py -q
```

Expected: pass.

**Step 2: Run frontend build**

Run:

```bash
cd frontend && npm run build
```

Expected: pass.

**Step 3: Optional manual verification**

Start existing dev stack if needed and verify:

- tool without example hides the example panel
- tool with `example_params` shows the panel
- preview opens text file
- use example fills parameters and binds files
- submit creates task with `file_ids`

### Commit Policy

Do not run `git commit` unless the user explicitly requests it. This repository's `AGENTS.md` forbids proactive git commit and branch operations.

