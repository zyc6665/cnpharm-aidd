# LVpocket Pocket Export Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 调整远端 `LVpocket-2` 的口袋残基导出逻辑，使 `protein_pocket_residues.pdb` 更接近示例 `pocket10.pdb` 的文件形式，并固定口袋截取大小为 `10A`。

**Architecture:** 仅修改远端容器 `kaiwu` 内 `/workspace/LVpocket-2/pocket_residue_export.py`。保留现有“根据 `pocket0.pdb` 反查蛋白残基”的数据流，但把距离阈值固定为 `10.0`，并在写出阶段保留 `CRYST1`/对应 `ANISOU`、补 `TER` 和 `END`，避免触碰平台侧文件收集逻辑。

**Tech Stack:** Python 3，SSH，Docker exec，PDB 文本处理

---

### Task 1: 锁定当前远端实现与目标差异

**Files:**
- Inspect: `/workspace/LVpocket-2/pocket_residue_export.py`
- Inspect: `/workspace/LVpocket-2/lvpocket_platform_predict.py`
- Inspect: `/data/zhouyc/kaiwu/platform-jobs/<task-id>/work/lvpocket_work/lvpocket_raw/input/protein_pocket_residues.pdb`

**Step 1: Read remote export code**

确认当前 `DEFAULT_DISTANCE_CUTOFF = 4.5`，以及 `_write_residue_pdb` 只输出 `ATOM/ANISOU` 命中行并补 `END`。

**Step 2: Capture baseline output traits**

记录当前导出文件是否含有 `CRYST1`、`ANISOU`、`TER`、`END`。

### Task 2: 实现固定 10A 与示例风格导出

**Files:**
- Modify: remote `/workspace/LVpocket-2/pocket_residue_export.py`

**Step 1: Change fixed cutoff**

把 `DEFAULT_DISTANCE_CUTOFF` 改成 `10.0`。

**Step 2: Preserve source header/records**

更新写出逻辑：
- 保留源文件中的 `CRYST1`
- 对选中残基保留 `ATOM` 与对应 `ANISOU`
- 在链或残基段结束后补 `TER`
- 文件末尾保留 `END`

**Step 3: Keep artifact contract unchanged**

不改 `protein_pocket_residues.pdb` 文件名、不改返回 JSON 字段结构。

### Task 3: 验证远端改动

**Files:**
- Inspect: remote generated `protein_pocket_residues.pdb`

**Step 1: Re-run export on an existing remote task directory**

直接调用远端 Python 对既有任务目录重跑导出逻辑，避免重新跑完整模型。

**Step 2: Verify file shape**

检查导出文件：
- 含 `CRYST1`
- 含 `END`
- 出现 `TER`
- 残基数量相较旧版本增大或不减少（10A 相比 4.5A）

**Step 3: Record results**

保留对比摘要，说明当前已接近示例形式，但内容仍然是“基于预测口袋点反查残基”的结果。
