# Model Card — std-diff-molecule-generation

## 定位

**本包为演示用 mock，数值不可用于科研决策。** 它只用于平台功能演示与前端联调。

## 输入 / 输出

- 输入：`pocket` (binding_pocket@1)
- 输出：`molecules` (molecule_table@1), `report` (run_report@1)
- 主表列名：smiles, inchi_key, mol_weight, logp, tpsa, hbd, hba, rotb, qed, sa_score, generation_score, rank

## 计算真实性

- **真算**（RDKit）：`mol_weight` / `logp` / `tpsa` / `hbd` / `hba` / `rotb` / `qed` / `inchi_key`，
  以及本包可用的 SA 近似分（`sa_score`）。RDKit wheel 未内置 `sascorer`，因此 `sa_score` 使用
  一个可解释的启发式（分子量 / 环数 / 立体中心 / 可旋转键），**不等价于原始的 SA score**。
- **确定性合成**（基于 `seed` + 输入哈希，可复现）：模型打分类字段（如 `generation_score`、
  `design_score`、`docking_score`、`admet_*`）以及 `md_trajectory` 的 `analysis_csv` / 伪 DCD、
  `gmx-mmpbsa-free-energy` 的 `delta_g_*`。
- 所有 `run_report@1` 产物的 `report.json` 都包含 `mock_disclaimer` 字段，明确说明「演示数据，
  不可用于科研决策」。

## 已知限制

- `trajectory.dcd` 是确定性占位字节流，不是合法的 DCD 二进制轨迹。
- `poses` 的 3D 坐标为 2D 布局生成的占位 SDF，不含真实对接构象。
- 未做任何实验验证；`haiguang-dcu` 变体 `hardware_validated: false`。
