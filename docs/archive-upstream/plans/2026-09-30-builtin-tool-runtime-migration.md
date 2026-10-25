# 平台内置工具运行时代码迁移计划

> **For Codex:** Resume this plan only after the user confirms the demo is complete. Use `superpowers:executing-plans` and `superpowers:test-driven-development` when implementation begins.

**目标：** 将平台内置工具的执行契约、领域处理器和运行时分发从 `backend/app/agents/aidd/builtin_tools.py` 分层迁移到 `backend/app/tool/`，保持平台任务、Workflow、Artifact 契约和工具行为不变，并彻底移除旧大模块及其兼容门面。

**架构：** `backend/app/tool/` 成为内置工具运行时包，按共享契约、分发注册和科学/数据领域处理器分层。`backend/app/tools/` 继续负责工具 schema 校验与版本管理；`backend/app/agents/aidd/capabilities.py` 继续声明 Agent 能力元数据；`backend/app/services/aidd_builtin_tools.py` 继续负责平台 Tool/ToolVersion 持久化及配置。运行时只依赖这些上层契约，不把工具管理、能力发现和科学算法混成一个包。

**技术栈：** Python 3.11+、pytest、Pydantic、RDKit、PDBFixer、OpenMM、Open Babel、现有 `StandardExecutionResult` / Artifact 契约。

---

## 执行时机与约束

- 当前阶段只保存规划；用户确认 Demo 完成后再开始源码迁移。
- Demo 阶段不重命名、不删除、不移动运行时模块，避免影响演示稳定性。
- 实施时不创建 Git 分支、不执行 `git commit`，除非用户另行要求。
- 迁移必须保持工具 slug、参数 schema、输入输出语义类型、Artifact role、relation、文件名及结果 metadata 的兼容性。
- 以测试先行的红—绿—重构循环迁移；不要通过保留 `agents/aidd/builtin_tools.py` 的完整 re-export 门面来假装完成清理。

## 目标目录

```text
backend/app/tool/
  __init__.py
  contracts.py
  artifact_refs.py
  registry.py
  protein_preparation/
    __init__.py
    handler.py
  ligand/
    __init__.py
    preparation.py
    conformer.py
  structure/
    __init__.py
    conversion.py
  docking/
    __init__.py
    vina.py
  rdkit/
    __init__.py
    properties.py
  external_databases/
    __init__.py
    fetch.py
    queries.py
  common/
    __init__.py
    serialization.py
```

现有 `backend/app/protein_preparation/engine.py`、`backend/app/chemistry/`、`backend/app/external_databases/` 保持为科学/数据访问核心；`app/tool/*/handler.py` 负责平台输入适配、调用领域核心、组装标准输出，不复制科学算法。

## 阶段 0：冻结行为与迁移清单

**涉及文件：** `test/test_aidd_builtin_tools.py`、`test/test_aidd_builtin_task_tools.py`、`test/test_artifact_binding_resolver.py`、`test/test_artifact_standard_registry.py`、`test/test_workflow_validation_standard_artifacts.py`。

1. 基于当前已通过的测试建立迁移前基线，记录所有可执行 builtin slug 和每个工具的 handler、参数、输入/输出角色。
2. 为 `run_builtin_tool` 增加 registry 覆盖测试：所有可执行 slug 均注册；未知 slug 和 placeholder slug 明确拒绝。
3. 固化蛋白准备、小分子准备、构象生成、结构转换、Vina、RDKit 属性和外部数据库工具的标准结果契约。
4. 记录仅被生产调用的 `run_vina_docking_with_tool`，迁移时同步修改 `backend/app/tasks/molecule_scoring.py`。

**验收：** 基线测试通过；没有任何输出契约变化。

## 阶段 1：建立运行时共享契约

**文件：** 新建 `backend/app/tool/contracts.py`、`backend/app/tool/artifact_refs.py`、`backend/app/tool/common/serialization.py` 及对应测试。

1. 先为 `BuiltinToolFile`、`BuiltinToolArtifact`、`BuiltinToolOutput`、`BuiltinToolResult` 编写契约测试。
2. 迁移 dataclass 到 `contracts.py`，保持字段、默认值和不可变性一致。
3. 迁移标准文件引用 SHA-256 生成到 `artifact_refs.py`，验证引用 hash 与实际内容一致。
4. 迁移 CSV/SDF/PDB 共用的纯序列化 helper；只抽取确实被多个领域共用的逻辑。

**验收：** 新契约测试通过；领域 handler 尚未迁移；无循环导入。

## 阶段 2：迁移蛋白、配体和结构转换工具

**文件：** 新建 `backend/app/tool/protein_preparation/handler.py`、`backend/app/tool/ligand/preparation.py`、`backend/app/tool/ligand/conformer.py`、`backend/app/tool/structure/conversion.py`；更新领域测试。

1. 先为 handler 的输入选择、参数验证和异常行为添加/调整测试。
2. 迁移 `builtin-protein-preparation` adapter；继续复用 `app/protein_preparation/engine.py`，保留 `prepared/degraded` 状态和报告行为。
3. 迁移 `builtin-ligand-preparation` adapter；继续复用 `app/chemistry/ligand_preparation.py`。
4. 迁移 `builtin-rdkit-conformer` adapter；复用配体规范化与三维构象核心。
5. 迁移 SDF→SMILES CSV、SDF→PDB、PDBQT 转换及其文件解析 helper 到 structure/conversion 或相关共用模块。

**验收：** 对应工具的 Artifact role、metadata、拒绝原因及三维坐标测试保持不变。

## 阶段 3：迁移对接、RDKit 与数据库工具

**文件：** 新建 `backend/app/tool/docking/vina.py`、`backend/app/tool/rdkit/properties.py`、`backend/app/tool/external_databases/fetch.py`、`backend/app/tool/external_databases/queries.py`；更新 `backend/app/tasks/molecule_scoring.py` 和领域测试。

1. 将 Vina 执行、PDBQT 转换及排序报告 handler 迁移到 `docking/vina.py`。
2. 将 `backend/app/tasks/molecule_scoring.py` 改为从新 docking 模块导入公开执行函数。
3. 迁移 RDKit 属性 handler；继续复用现有 chemistry 核心与 CSV/report 契约。
4. 将 Fetch PDB、Fetch ligand 和 ChEMBL/PubChem/PDBBind 查询 handler 按 fetch 与 query 分层。
5. 通过测试验证外部 provider 调用失败、空结果和 Artifact lineage 行为不变。

**验收：** 生产代码不再从旧大模块导入任何函数；上述领域测试通过。

## 阶段 4：集中注册与任务执行入口切换

**文件：** 新建 `backend/app/tool/registry.py`、`backend/app/tool/__init__.py`；修改 `backend/app/tasks/executors/builtin.py`；更新 registry/dispatcher 测试。

1. 以显式 slug→handler 映射注册当前真实可执行 builtin，不注册未实现的科学能力。
2. 将原 `run_builtin_tool` 分支分发改为新包的公开执行入口；区分同步 handler 的线程执行和异步外部数据库 handler。
3. 把 `BuiltinToolFile`、`BuiltinToolResult` 和公开 dispatch 通过 `app.tool` 明确导出。
4. 更新 `BuiltinExecutor` 从 `app.tool` 调用，不让任务执行层依赖 Agent 包。
5. 测试工具 slug 全覆盖、未知工具错误、placeholder 拒绝和 handler 执行线程策略。

**验收：** Worker 执行入口只依赖 `app.tool`；Tool/Workflow 标准契约不变。

## 阶段 5：清除旧模块与不可达伪 handler

**文件：** 删除 `backend/app/agents/aidd/builtin_tools.py`；整理 `test/test_aidd_builtin_tools.py` 为按领域组织的测试；检查 `backend/app/agents/aidd/`、`backend/app/tasks/` 所有 import。

1. 将旧测试中的内部函数导入改为领域模块公开接口或 handler 测试，不引入仅供旧路径兼容的门面。
2. 移除旧文件中的重复 dataclass、重复 dispatcher 和已确认没有注册入口的伪执行 handler。
3. 保留能力 placeholder 声明及其“不可执行”测试，但不保留会生成看似科学结果的不可达假 handler。
4. 全仓搜索旧模块路径与旧 handler 名称，清理所有生产、测试及文档中的失效引用。

**验收：** 删除旧文件后，生产导入、测试收集和工具执行均正常；没有循环导入或双重注册。

## 阶段 6：集成验收与文档收尾

**测试命令：**

```bash
pytest -q test/test_tool_runtime_contracts.py test/test_tool_runtime_registry.py
pytest -q test/test_aidd_builtin_tools.py test/test_aidd_builtin_task_tools.py
pytest -q test/test_artifact_binding_resolver.py test/test_artifact_standard_registry.py test/test_workflow_validation_standard_artifacts.py
pytest -q test/test_protein_preparation_engine.py test/test_protein_preparation_schemas.py test/test_ligand_preparation.py test/test_ligand_preparation_schemas.py
python -m compileall -q backend/app
git diff --check
```

1. 执行以上 focused tests，再运行与任务执行、Artifact 持久化相关的扩展测试。
2. 搜索确保 `app/agents/aidd/builtin_tools.py`、旧 dispatcher 和旧私有 handler import 已完全消失。
3. 更新架构文档说明 `app/tool` runtime、`app/tools` management、`app/agents/aidd` capability discovery 的职责边界。
4. 检查工作区 diff，仅保留运行时代码迁移及其测试/文档改动；不提交。

## 完成标准

- 全部真实可执行的 builtin handler、共享执行契约和运行时 dispatcher 位于 `backend/app/tool/`，并按领域分层。
- `BuiltinExecutor` 与分子评分任务使用新运行时路径。
- 旧 `backend/app/agents/aidd/builtin_tools.py` 已删除，无兼容 re-export 门面。
- Tool slug、参数、标准 Artifact 输出和工作流绑定行为与迁移前一致。
- 未实现的 placeholder 仍被拒绝，不生成伪造科学结果。
- focused tests、compileall 和 diff 检查全部通过。
- Demo 未完成前不开始上述源码迁移；启动时以该文档作为实施清单。
