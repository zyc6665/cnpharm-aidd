# Model Platformization Template

这个目录是把旧模型代码整理成平台 Tool Package v2 的可复制模板。目标只有一个：
**平台契约固定，模型部署包适配平台**。以后接入 LVpocket、Pocket2Mol 或其他模型时，
优先改模型 wrapper、输入处理和输出处理，不要修改平台后端或前端。

## 固定边界

- `tool.yaml` 只声明平台标准 Artifact：输入 `protein_structure@1`，输出
  `binding_pocket@1` 和可选 `run_report@1`。
- `binding_pocket@1` 必须包含三个文件角色：`residue_pocket_pdb`、
  `atom_pocket_pdb`、`pocket_metadata_json`。
- Agent、workflow、存储、渲染、校验、可视化只识别标准类型和文件角色，不识别旧模型私有字段。
- `runtime` 必须声明 Runtime Env：首选 container 镜像 digest、conda-pack fallback、
  权重 manifest SHA-256 和缓存 key。
- 旧模型的参数、路径、权重选择和后处理逻辑放进 `runner/` 或远端部署代码，不扩散到平台。
- 真实硬件没有跑过黄金样例前，`validation_status` 保持 `unvalidated` 或
  `adapted_pending_hardware_validation`。

## Runtime Env

Tool Package v2 的 `runtime` 字段是部署时的运行环境契约。Executor 不安装依赖，也不依赖
宿主机私有 conda 路径；它只选择已声明的 Runtime Env，挂载输入、输出、工作目录和权重，
然后调用 `runner/entrypoint.sh`。

部署新模型时必须替换模板中的示例值：

- `runtime.artifacts.primary.image_digest`：生产容器的不可变镜像 digest。
- `runtime.artifacts.fallback.sha256`：conda-pack 或 venv-pack 的 SHA-256。
- `runtime.weights.manifest_sha256`：权重 manifest 的 SHA-256。
- `runtime.cache_policy.key_fields`：至少包含 runtime digest 和权重 manifest SHA。

## 适配流程

1. 复制本目录为新模型包，修改 `metadata.slug`、`name`、`version` 和参数 schema。
2. 在旧模型代码外包一层 adapter：读取平台 `request.v1`，把标准输入转换成旧模型需要的文件布局。
3. 更新 `tool.yaml.runtime`，填入镜像 digest、fallback SHA、权重 manifest 和缓存策略。
4. 执行旧模型原始入口，收集原始输出。
5. 把原始输出转换成标准输出：
   - 残基级口袋 PDB 写到 `artifacts/pocket/residue_pocket.pdb`
   - 原子级口袋 PDB 写到 `artifacts/pocket/atom_pocket.pdb`
   - 口袋元数据 JSON 写到 `artifacts/pocket/pocket_metadata.json`
6. 写 `output/result.json`，格式与 `schemas/result.v2.example.json` 一致。
7. 跑包内测试和平台校验，再登记为工具版本。

## LVpocket 改造重点

LVpocket 原始口袋可能来自体素或点云后处理，不能直接当成下游分子生成模型需要的残基级口袋。
部署 LVpocket 时，adapter 必须补齐：

- `residue_pocket_pdb`：从原蛋白结构按口袋坐标、半径或残基映射导出完整残基上下文。
- `atom_pocket_pdb`：保留适合可视化、dock 或坐标模型使用的口袋原子/点位结构。
- `pocket_metadata_json`：至少包含 `center`、`bbox`、`residue_ids`、`atom_ids`、
  `source_protein_ref`。

## 验证命令

从仓库根目录运行：

```bash
pytest test/test_model_platformization_template.py \
  example/model-platformization-template/tests/test_contract.py -q
```

从 `backend/` 运行平台 manifest 校验：

```bash
python -m app.tool_packages.validator ../example/model-platformization-template
```

这些命令只证明契约和样例结构正确，不代表模型科学结果或硬件兼容已经验证。
