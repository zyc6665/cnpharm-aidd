# 工具参数契约与注册流程实施计划

> 本计划对应已确认的《工具参数契约与注册流程设计》。

**目标：** 使用公开 Tool Contract 驱动运行表单，并让管理员通过结构化编辑器为新工具定义经过后端校验的参数 Schema。

**架构：** 新增共享 Schema 编辑组件并保留高级 JSON 兼容入口；公开 Contract 成为工具详情和工作流运行的首选数据源；Tool Package v2 在 Pydantic 入口验证 Draft-07 Schema，平台资源配置继续留在执行 variants/runtime。

**技术栈：** Vue 3、TypeScript、Ant Design Vue、FastAPI、Pydantic、jsonschema Draft-07。

---

### 任务 1：让运行页读取公开 Contract

**状态：已完成**

**文件：**
- 修改 `frontend/src/domain/tools/tool-run-input-surface.ts`
- 修改 `frontend/src/composables/useToolDetailPresentation.ts`
- 修改 `frontend/src/views/tools/Detail.vue`
- 检查 `frontend/src/domain/tools/standard-artifact-inputs.ts`

**步骤：**
1. 读取 `contract.schema.input/output` 和 `contract.executor.type`。
2. 保留旧内部响应的 config fallback。
3. 确认 Tool Package 标准 Artifact 槽仍单独显示，且参数 schema 不从 config 读取。
4. 在详情页导入现有 `ToolDetailOverview`，避免未注册组件。

### 任务 2：实现共用结构化参数编辑器

**状态：已完成**

**文件：**
- 新建 `frontend/src/components/tools/ToolParameterSchemaEditor.vue`
- 修改 `frontend/src/views/tools/Create.vue`
- 修改 `frontend/src/views/admin/ToolPackages.vue`
- 修改 `frontend/src/domain/tool-packages/manifest.ts`

**步骤：**
1. 编辑字段名、标题、类型、必填、默认值、说明、枚举和数值范围。
2. 加入高级 JSON 模式；解析失败时阻止提交，并保留原 Schema 的未知扩展字段。
3. 将旧工具 input_schema 文本框替换为共享编辑器。
4. 为 Tool Package 向导加入参数字段列表，由草稿生成 `parameters_schema`，并支持高级 JSON 查看/编辑。
5. 在向导中将科学参数与标准 Artifact/资源配置分区展示。

### 任务 3：后端校验 Tool Package 参数 Schema

**状态：已完成**

**文件：**
- 修改 `backend/app/tools/schema_validator.py`
- 修改 `backend/app/tool_packages/schemas.py`
- 修改 `backend/app/tool_packages/validator.py`

**步骤：**
1. 抽取可复用的 Draft-07 Schema 定义校验入口。
2. 在 Tool Package v2 的参数 Schema 解析阶段检查 Draft-07、object 根类型和 required 引用。
3. 返回含字段路径的可读校验错误，并拒绝平台执行字段混入必填科学参数。

### 任务 4：整理用户运行表单信息层级

**状态：已完成**

**文件：**
- 修改 `frontend/src/components/tools/ToolParameterForm.vue`
- 修改 `frontend/src/components/tools/StandardArtifactInputs.vue`
- 必要时修改 `frontend/src/types/models.d.ts`

**步骤：**
1. 删除输入框 placeholder 与表单说明重复的呈现。
2. 标准 Artifact 输入优先展示可读标题/说明，并保留名称作为内部绑定键。
3. 不改动当前详情页布局和项目输入行为。

### 任务 5：检查与文档

**状态：已完成**

**文件：**
- 更新本设计与实施计划文档

**步骤：**
1. 运行前端生产构建，确认 Vue/TypeScript 编译。
2. 运行 `git diff --check` 检查补丁格式。
3. 检查最终 diff 和工作区状态，确认没有覆盖已有改动；不创建 Git 提交。
