# Pocket Receptor Cartoon Design

**背景**

任务详情页当前会把输入口袋受体和输出小分子一起送入 Mol*，但没有按语义区分表示方式。对 `protein_pocket_residues.pdb` 这类受体输入，Mol* 默认表现会更接近通用分子原子视图，不符合口袋残基的预期展示。

**目标**

只调整输入受体结构的展示方式：
- `receptor` 输入使用 `cartoon`
- 隐藏受体的默认球棍表现
- 输出小分子继续保持现有展示方式

**方案**

沿用现有前端语义分层，不新增后端字段：
- 继续使用 `result-visualization.ts` 已经产出的 `role === 'receptor'`
- 在 `MoleculeViewer.vue` 加载结构时，若条目是 `receptor`，则向 Mol* 传入 `polymer-cartoon` 表示 preset
- 其他条目维持原行为，避免影响配体显示

**验证**

新增前端测试，锁定 `MoleculeViewer.vue` 中存在受体专用 `polymer-cartoon` 逻辑，并跑对应测试文件验证。
