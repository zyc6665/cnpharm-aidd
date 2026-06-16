# Tool Markdown Introduction Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add versioned Markdown tool introductions editable in admin and rendered in the public tool detail modal.

**Architecture:** Store Markdown in `ToolVersion.config.documentation_markdown`, because tool parameters and outputs are already version-scoped. Add a small frontend Markdown rendering helper that escapes raw HTML and a fallback document builder that derives content from `input_schema`, `output_schema`, and `output_globs`. Extend the existing create/edit form and detail page without adding backend tables or endpoints.

**Tech Stack:** Vue 3, TypeScript, Ant Design Vue, Pinia store, Node test runner, current FastAPI backend response shape.

---

### Task 1: Add Markdown Rendering and Fallback Document Helpers

**Files:**
- Create: `frontend/src/views/tools/tool-documentation.ts`
- Test: `frontend/test/tool-documentation.test.ts`

**Step 1: Write failing tests**

Cover these cases:

- `renderMarkdownToHtml` escapes `<script>` instead of executing or preserving raw HTML.
- headings, lists, fenced code, inline code, links, and tables render to HTML.
- `buildFallbackToolDocumentation` includes tool description, input parameter names, output schema fields, and `output_globs`.

**Step 2: Run tests to verify failure**

Run:

```bash
cd frontend && node --test test/tool-documentation.test.ts
```

Expected: FAIL because `tool-documentation.ts` does not exist.

**Step 3: Implement helper module**

Create `frontend/src/views/tools/tool-documentation.ts` with:

- `renderMarkdownToHtml(markdown: string): string`
- `buildFallbackToolDocumentation(options): string`
- internal escaping helpers
- no raw HTML support

Use a minimal local renderer to avoid adding dependencies unless a future richer editor requires one.

**Step 4: Run tests**

Run:

```bash
cd frontend && node --test test/tool-documentation.test.ts
```

Expected: PASS.

**Step 5: Do not commit**

Do not run `git commit` unless the user explicitly requests it.

### Task 2: Extend Admin Create/Edit Form

**Files:**
- Modify: `frontend/src/views/tools/Create.vue`
- Test: `frontend/test/tool-markdown-admin-surface.test.ts`

**Step 1: Write failing source-surface test**

Assert `Create.vue` contains:

- `documentation_markdown` form state
- `config.documentation_markdown`
- `t('tools.documentationMarkdown')`
- markdown editor textarea class or section marker

**Step 2: Run test to verify failure**

Run:

```bash
cd frontend && node --test test/tool-markdown-admin-surface.test.ts
```

Expected: FAIL before implementation.

**Step 3: Implement admin form changes**

In `Create.vue`:

- Add `documentation_markdown: string` to `ExtendedFormState`.
- Initialize it to `''`.
- In `parseToolConfigIntoForm`, read `config.documentation_markdown` when it is a string.
- In `handleSubmit`, include `config.documentation_markdown` when non-empty.
- Add a form section after parameter schema inputs or near version info with Markdown textarea and concise helper copy.

**Step 4: Run tests**

Run:

```bash
cd frontend && node --test test/tool-markdown-admin-surface.test.ts
```

Expected: PASS.

**Step 5: Do not commit**

Do not run `git commit` unless the user explicitly requests it.

### Task 3: Add Detail Page Introduction Modal

**Files:**
- Modify: `frontend/src/views/tools/Detail.vue`
- Test: `frontend/test/tool-markdown-detail-surface.test.ts`

**Step 1: Write failing source-surface test**

Assert `Detail.vue` contains:

- `documentationOpen`
- `renderMarkdownToHtml`
- `buildFallbackToolDocumentation`
- `tools.viewIntroduction`
- `tool-documentation-modal`
- `v-html="documentationHtml"`

**Step 2: Run test to verify failure**

Run:

```bash
cd frontend && node --test test/tool-markdown-detail-surface.test.ts
```

Expected: FAIL before implementation.

**Step 3: Implement modal**

In `Detail.vue`:

- Add a “工具介绍” button in `AppPageHeader` actions.
- Add modal after the existing preview modal.
- Add computed `toolDocumentationMarkdown` that prefers `config.documentation_markdown`, otherwise uses fallback builder.
- Add computed `documentationHtml` using `renderMarkdownToHtml`.
- Style `.tool-documentation-content` for readable Markdown in the modal.

**Step 4: Run tests**

Run:

```bash
cd frontend && node --test test/tool-markdown-detail-surface.test.ts
```

Expected: PASS.

**Step 5: Do not commit**

Do not run `git commit` unless the user explicitly requests it.

### Task 4: Update I18n and Run Verification

**Files:**
- Modify: `frontend/src/locales/zh-CN/index.ts`
- Modify: `frontend/src/locales/en-US/index.ts`

**Step 1: Add locale keys**

Add:

- `tools.viewIntroduction`
- `tools.documentationMarkdown`
- `tools.documentationMarkdownHint`
- `tools.noDocumentation`
- any small labels needed by fallback Markdown.

**Step 2: Run focused frontend tests**

Run:

```bash
cd frontend && node --test test/tool-documentation.test.ts test/tool-markdown-admin-surface.test.ts test/tool-markdown-detail-surface.test.ts test/tool-detail-page-polish.test.ts test/tool-detail-schema.test.ts
```

Expected: PASS.

**Step 3: Run type/build verification**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS.

**Step 4: Do not commit**

Do not run `git commit` unless the user explicitly requests it.
