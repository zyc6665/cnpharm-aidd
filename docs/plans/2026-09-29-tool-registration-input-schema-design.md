# 工具参数契约与注册流程设计

## 目标

让管理员通过结构化表单定义新工具参数，减少 JSON Schema 手工配置错误；让工具详情与工作流运行表单只依赖公开 Tool Contract，不依赖公开接口不再返回的运行时配置。

## 边界

- 用户运行时填写的科学参数属于 `parameters_schema` / `input_schema`。
- 标准 Artifact 输入输出、执行器、资源、凭证和运行环境属于平台契约，不混入科学参数表单。
- Tool Package v2 是新模型工具的主注册路径；旧工具管理保留为兼容路径。
- 本次不实现 GitHub 仓库扫描、镜像构建或自动部署。

## 方案

### 运行契约

公开详情页和工作流节点优先读取 `tool.contract.schema.input`、`tool.contract.schema.output`、`tool.contract.executor.type` 以及 `tool.contract.artifacts`。只有旧内部响应没有 Contract 时才回退到 `current_version.config`。Tool Package 的参数 schema 同样从 Contract 读取，避免前端依赖内部 manifest/config。

### 参数编辑

新增共用结构化参数编辑器，供旧工具创建/编辑页和 Tool Package v2 向导使用。编辑器支持字段名、标题、类型、必填、默认值、说明、枚举选项、数值范围和字符串格式；结构化更新保留未识别的 JSON Schema 扩展字段。高级 JSON 编辑入口用于迁移既有复杂 Schema。

Tool Package 向导将标准 Artifact 槽与科学参数分开配置，真实生成 `parameters_schema`，并允许查看/编辑参数 Schema 的高级 JSON。资源档位和加速器仍由 variants/runtime 字段管理。

### 校验

后端在 Tool Package v2 参数 Schema 入口复用 Draft-07 Schema 校验，继续验证参数根类型、必填字段引用和平台管理字段边界。错误在创建前返回明确字段路径，避免无效 Schema 进入已登记版本。

### 详情表单

参数说明只显示一次；详情页显式注册概览组件。标准 Artifact 输入用可读标签展示，保留契约名称作为提交键。参数字段仍由各工具自己的公开 schema 决定，不按工具 slug 硬编码表单。

## 方案比较

1. 仅让运行页读取公开 Contract：改动最少，但管理员仍需手写 Schema，新增工具容易出错。
2. 完整无代码注册向导并自动分析 GitHub 仓库：自动化程度高，但需要新增仓库分析、镜像构建和发布流程，超出当前平台演示目标。
3. 共用结构化 Schema 编辑器并由 Contract 驱动运行表单：覆盖当前数据链路和常见录入错误，保留高级 JSON 兼容方式，改动规模适中。本项目采用此方案。

## 验收标准

- 公开工具接口没有 `current_version.config` 时，运行表单仍能显示 schema 参数并使用正确 executor type 提交。
- Tool Package v2 向导能生成非空 `parameters_schema`，并支持常见参数类型和必填/默认/选项/范围/说明。
- 旧工具配置可以打开、编辑并保留未识别的 Schema 属性。
- 无效 Draft-07 Schema 和无效 required 引用不能登记为有效 Tool Package。
- 用户界面不把资源档位或凭证当作模型科学参数输入项。

## 风险与取舍

- 遗留工具可能依赖非标准 Schema 扩展；高级 JSON 入口和属性合并用于避免编辑时丢失这些字段。
- 已有 Tool Package 中可选的 `device` 参数暂作兼容保留；新向导会将 `device` 作为平台字段拦截，后续迁移时应由执行 variants 决定设备。
- 公开 Contract 是运行页面的稳定接口。以后新增参数展示行为应先扩展契约字段和 Schema 元数据，再改页面组件，避免再次依赖私有 config。
