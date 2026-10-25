# Home PAIWSIT Integration Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add PAIWSIT to the homepage foundation section, reorder the section to `PAIWSIT -> CPUPDB -> CPUModel`, and update copy and layout to present target discovery before structure data and platform execution.

**Architecture:** Keep the current homepage structure and extend the existing `foundation-section` from two cards to three. Reuse the current reveal and panel patterns, add one emphasized PAIWSIT card, and update i18n so the structure stays static and content-driven.

**Tech Stack:** Vue 3 SFC, Vue I18n, Ant Design Vue, existing Node source-surface tests.

---

### Task 1: Update Homepage Surface Test

**Files:**
- Modify: `frontend/test/home-cpupdb-aidd.test.ts`
- Test: `frontend/test/home-cpupdb-aidd.test.ts`

**Step 1: Write the failing test**

Add assertions for:

- `PAIWSIT` content in `src/views/home/index.vue`
- `http://www.paiwsit.com/` link
- `foundation-panel-paiwsit`
- `foundation-panel-cpupdb`
- `foundation-panel-platform`
- `PAIWSIT` appearing before `CPUPDB`, and `CPUPDB` before `CPUModel`

**Step 2: Run test to verify it fails**

Run:

```bash
cd frontend && node --test test/home-cpupdb-aidd.test.ts
```

Expected: FAIL before implementation.

**Step 3: Do not commit**

Do not run `git commit` unless explicitly requested.

### Task 2: Update Locale Copy

**Files:**
- Modify: `frontend/src/locales/zh-CN/index.ts`
- Modify: `frontend/src/locales/en-US/index.ts`

**Step 1: Add and reorder foundation copy**

Update:

- `home.foundation.title`
- `home.foundation.subtitle`
- `home.foundation.paiwsit.*`
- `home.foundation.cpupdb.*`
- `home.foundation.platform.*`

Make sure the copy clearly maps to:

- target discovery entry
- structural pocket foundation
- computational workbench

**Step 2: Keep existing action semantics**

- `PAIWSIT`: external link
- `CPUPDB`: external link and help link
- `CPUModel`: internal `/workflow`

**Step 3: Do not commit**

Do not run `git commit` unless explicitly requested.

### Task 3: Implement Homepage Layout Change

**Files:**
- Modify: `frontend/src/views/home/index.vue`
- Test: `frontend/test/home-cpupdb-aidd.test.ts`

**Step 1: Implement three-card foundation layout**

Change the section so:

- `PAIWSIT` card renders first
- `CPUPDB` card renders second
- `CPUModel` card renders third

Add a dedicated emphasized class for the first card such as `foundation-panel-paiwsit`.

**Step 2: Update supporting script state**

Adjust any supporting arrays or constants so they follow the new ordering and keep point lists separated by card.

**Step 3: Update styles**

Reuse the current section style language, but:

- make the `PAIWSIT` card visually stronger
- keep the section responsive
- preserve the existing reveal timing behavior

**Step 4: Run test to verify it passes**

Run:

```bash
cd frontend && node --test test/home-cpupdb-aidd.test.ts
```

Expected: PASS.

**Step 5: Do not commit**

Do not run `git commit` unless explicitly requested.

### Task 4: Run Verification

**Files:**
- Verify existing edits only

**Step 1: Run focused tests**

Run:

```bash
cd frontend && node --test test/home-cpupdb-aidd.test.ts test/app-page-header-surface.test.ts
```

Expected: PASS.

**Step 2: Run full frontend build**

Run:

```bash
cd frontend && npm run build
```

Expected: PASS.

**Step 3: Do not commit**

Do not run `git commit` unless explicitly requested.
