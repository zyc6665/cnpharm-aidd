# Prompt for Codex or Claude Model Platformization

你正在把一个旧模型代码库整理成 SciMiner 模型侧规范包，并为它配套一个
Tool Package v2 声明。请严格按以下规则执行。

## 目标

平台契约固定，模型代码适配平台。不要修改平台后端或前端，不要为单个模型新增平台字段。
适配逻辑必须放在模型侧 `model/<Model>/src/<runtime>`，并由
`model/<Model>/platform_run.sh` 暴露统一入口。Tool Package runner 只能委托这个入口。

## 必须保持的标准契约

- 输入槽：`protein`，类型 `protein_structure@1`
- 输出槽：`pocket`，类型 `binding_pocket@1`
- 可选输出槽：`report`，类型 `run_report@1`
- `binding_pocket@1` 必须写出：
  - `residue_pocket_pdb`
  - `atom_pocket_pdb`
  - `pocket_metadata_json`
- `pocket_metadata_json` 至少包含：
  - `center`
  - `bbox`
  - `residue_ids`
  - `atom_ids`
  - `source_protein_ref`

## 工作步骤

1. 先阅读模型侧规范包模板 `example/model-package-template`、当前目录的 `tool.yaml`、`README.md` 和测试。
2. 阅读旧模型入口脚本，找出它实际需要的输入文件、参数、工作目录和输出文件。
3. 在 `model/<Model>/src/<runtime>` 中实现输入转换：把平台 request 里的标准 Artifact 文件挂载或复制到旧模型需要的位置。
4. 通过 `model/<Model>/platform_run.sh` 执行旧模型原始入口，不改变平台 request/result 格式。
5. 在模型侧 runtime 中实现输出转换：把旧模型输出转为 `binding_pocket@1` 的三个标准文件角色。
6. 保持 Tool Package `runner/entrypoint.sh` 极薄，只委托模型侧 `platform_run.sh`，不要放模型私有逻辑。
7. 更新 `tool.yaml.runtime`：Runtime Env 必须包含镜像 digest、conda-pack/venv-pack fallback、
   权重 manifest SHA-256 和缓存 key；Executor 不安装依赖。
8. 更新 `schemas/result.v2.example.json` 和 `examples/output/result.json` 的路径、哈希与 metadata。
9. 补充模型包契约测试，覆盖至少一个成功输出和一个缺失必需文件的失败路径。
10. 运行验证命令，失败时修模型侧 runtime 或测试，不要放宽平台契约。

## LVpocket 特别要求

如果旧模型是 LVpocket，不能把体素转出的原始 PDB 直接作为唯一口袋交给下游生成模型。
必须额外从原蛋白结构导出残基级口袋 `residue_pocket_pdb`，并保留原子级或坐标级口袋
`atom_pocket_pdb`。metadata 需要记录口袋中心、包围盒、残基 ID、原子 ID 和来源蛋白引用。

## 禁止事项

- 禁止新增 `pocket_pdb`、`pocket_result` 等新主路径类型。
- 禁止让 Agent 或 workflow 填写模型私有语义映射。
- 禁止把模型 adapter 或旧模型推理代码放进 Tool Package runner。
- 禁止把运行设备作为必填业务参数；设备属于 variant 执行上下文。
- 禁止声明未验证硬件为 `validated`。
- 禁止提交凭据、私有地址、宿主机绝对路径或无法复现的本地文件引用。
- 禁止把宿主机 conda 路径当成 Runtime Env；必须在 manifest 中声明可校验的运行环境产物。
