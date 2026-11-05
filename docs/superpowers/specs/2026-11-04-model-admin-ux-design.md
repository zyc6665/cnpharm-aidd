# 模型管理 / 编辑 / 版本变更 UX 重设计（k8s-only）

- 日期：2026-11-04
- 状态：设计待评审（未实现）
- 关联：`docs/07-模型交付与运行规范.md`、`docs/23-模型接入操作手册`、`frontend/src/views/tools/Create.vue`、`frontend/src/views/admin/Tools.vue`、`backend/app/execution/adapters/kubernetes_manifest.py`
- 目标架构：**模型统一通过 k8s_job 调度**（Docker/SSH/Python 执行器不再作为管理员选项）

## 1. 为什么改（intent）

当前「模型编辑」页是**执行器为中心**的旧表单：顶部有 `工具类型：Docker镜像 / Python脚本 / SSH作业 / Kubernetes Job` 四选一，下面按类型展开 Docker/Python/SSH/K8s 四套配置，末尾还有「旧版 Agent 语义映射（兼容）」。

但平台现状与后续方向已经明确：

- 工具版本 `config.type = k8s_job`；GPU 以 `nvidia.com/gpu` 由 K8s 调度（`kubernetes_manifest.py`）；`factory._allocate_gpu` 对 k8s_job 直接跳过 slots/agent；
- 服务器（k3s-4090）已按 K8s Job 运行；
- 继续暴露四类执行器和旧 Agent 语义映射，只会让管理员误选、填错、产生平台永远不消费的配置。

因此从**管理员**和**开发**两个角度，编辑页应转为**模型契约为中心、k8s 唯一执行**的向导式表单，并把“怎么做镜像 / 怎么符合输入输出规范”做成**内置教程 + 字段校验**。

## 2. 目标 / 非目标 / 反目标

**目标**
1. 管理员 5 步内完成一个新模型的上架；每步可校验、可保存草稿。
2. 只保留 k8s 唯一执行路径；删除工具类型选择与旧 Agent 语义映射。
3. 以 Tool Package v2（`aidd.sciminer/tool-package`）为标准：输入/输出用平台标准 Artifact 类型，运行参数用 `parameters_schema`。
4. 版本变更清晰：查看历史版本、基于当前版本“新建版本”、发布/停用、变更说明必填。
5. 内置「模型接入教程」helper：镜像构建 → 入口/权重 → Tool Package 契约 → 发布 → 冒烟。

**非目标**：不改后端执行/调度算法；不引入新执行器；不重写 kubectl 侧。

**反目标**：仍让管理员面对四类执行器；编辑页仍是“一屏长表单”；版本变更靠改同一版本。

## 3. 信息架构（IA）

### 3.1 工具管理（模型列表）
列：名称 / slug / **能力族**（model_family）/ 分类 / **当前版本** / **镜像 digest** / 状态 / 更新时间 / 操作。
操作：新建模型、发布新版本、查看版本、停用/删除、查看接入教程。
筛选：能力族、分类、状态、关键词。

### 3.2 模型编辑（向导，左侧步骤 + 右侧固定摘要）
```
① 基本信息        名称、slug、能力族、分类、标签、图标、简介
② 镜像与运行       镜像(建议 digest)、启动命令、环境变量、资源画像(CPU/内存/GPU/显存)、超时、权重挂载
③ 输入/输出契约    Tool Package v2 artifacts（标准类型、必填、role_preferences）
④ 运行参数         parameters_schema（表单编辑 + 高级 JSON）
⑤ 版本与发布       版本号、变更说明、与当前版本 Diff、保存草稿 / 发布、冒烟测试
```
- 顶部固定「查看接入教程 / 查看规范」入口（helper drawer）。
- 每步右侧校验状态；未通过不允许进入“发布”。
- **移除**：`工具类型` 四选一、Python/SSH/Docker 专属配置区、`旧版 Agent 语义映射（兼容）`。

### 3.3 版本变更
- 版本不可变：已发布版本只读；变更=“基于当前版本新建版本”（复制配置 + 填新版本号 + 变更说明）。
- 版本列表（抽屉）：版本号、状态（当前/历史/已弃用）、镜像 digest、发布时间、变更说明、操作（设为当前/弃用/查看 Diff）。
- 发布前校验：镜像 digest 存在、输入输出类型合法、`parameters_schema` 合法、资源画像齐全、冒烟通过。

## 4. 关键页面行为

### 4.1 编辑 = 向导
- 左栏步骤条 + 状态徽标（未填/待校验/通过）；右栏实时摘要（slug、能力族、镜像、输入输出数量、版本）。
- 「保存草稿」任意步骤可用；「发布」仅第⑤步且全步通过。
- 每步“校验”：前端 schema + 可选后端 dry-run（校验 ToolPackage 与资源画像）。

### 4.2 Helper（内置教程抽屉）
分 5 节，可复制命令：
1) 镜像构建（CUDA/驱动基座、只装运行依赖、ENTRYPOINT 固定、权重外置 `runtime.weights.mounts`、禁止绝对宿主路径）；
2) 入口与产物（只写 `/work/out`，`result.json`/`progress.json` 约定，退出码语义）；
3) Tool Package v2 示例（见教程文档）；
4) 标准 Artifact 类型对照表（protein_structure@1 / binding_pocket@1 / molecule_table@1 / ligand_structure@1 / run_report@1 …）；
5) 发布与冒烟（镜像推 registry → 新建版本 → 冒烟任务 → 设为当前）。

### 4.3 删除项
- 工具类型选择器 → 固定 `k8s_job`（页面不显示）。
- Python 脚本 / SSH 作业 / Docker 专属执行器表单 → 不再渲染。
- 旧版 Agent 语义映射（兼容）→ 删除（输入/输出语义由 Tool Package artifacts 承担）。

## 5. 开发实现要点

- 前端 `Create.vue`：`formState.tool_type` 固定 `k8s_job`、隐藏选择器；移除 agent 语义映射相关表单块与提交字段；保留 K8s 配置（镜像/命令/env/resource_profile/timeout）。
- 表单域拆分：`domain/tools/tool-create-form.ts` 保留 ToolPackage v2 组装；删除 agent capability 组装的 UI 入口（后端字段保留兼容，不再从编辑页写入）。
- 新增只读校验接口（可选）：`POST /api/v1/tools/validate-package` 返回 ToolPackage/资源画像校验结果（复用后端 manifest 校验）。
- 版本：复用现有 tool_versions API；新增“基于版本 N 新建版本”为前端复制 + createToolVersion。
- 后端：不改 `k8s_job` 执行；`config.type` 恒为 `k8s_job`。

## 6. 迁移与兼容
- 现有工具配置 `type` 已是 `k8s_job`；编辑时不再展示其它类型，保存时强制 `k8s_job`。
- 旧 Agent 字段（`agent_capability`）保留在数据中但编辑页不再读写；后续如确认无消费者再清理。
- Python/SSH 执行器代码保留（后台能力），仅从“新建/编辑模型”的管理入口隐藏。

## 7. 验收
- 管理员从“新建模型”到“发布”全程无需接触 Docker/Python/SSH/Agent 语义项。
- 任一版本发布前必须通过：镜像/资源/输入输出/参数/冒烟。
- 版本历史可查看、可新建版本、可弃用；旧版本配置不被就地修改。
- 教程抽屉可完成一次镜像构建→发布的自助接入。
