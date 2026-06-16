# 工具 Markdown 介绍设计

## 目标

为工具详情页增加可由后台维护的 Markdown 介绍。管理员在工具编辑页编写介绍文档，用户在工具详情页点击“工具介绍”后，通过弹窗查看渲染后的 Markdown 内容。文档随工具版本配置保存，保证介绍、参数和输出说明与当前模型版本一致。

## 推荐方案

把 Markdown 内容保存到 `ToolVersion.config.documentation_markdown`。

这样不需要新增数据库字段，也不需要新增后端接口。现有工具创建/编辑页已经会创建新版本，详情页已经能读取 `current_version.config`，因此只需要扩展前端表单和详情页展示逻辑。

## 后台管理

在 `frontend/src/views/tools/Create.vue` 的工具创建/编辑页增加“介绍文档”区域：

- 使用多行文本框录入 Markdown。
- 编辑工具时，从 `tool.current_version.config.documentation_markdown` 回填。
- 保存工具时，把内容写入版本配置。
- 修改介绍文档会被视为版本配置变化，需要填写新版本号并创建新版本。

## 前台详情页

在 `frontend/src/views/tools/Detail.vue` 增加“工具介绍”按钮和弹窗：

- 按钮放在详情页页头操作区，和收藏按钮、版本标签保持同一交互层级。
- 弹窗优先渲染 `documentation_markdown`。
- 如果没有配置 Markdown，则自动生成兜底说明，包括工具描述、输入参数、输出 Schema 或输出路径规则。

## Markdown 渲染

渲染逻辑放在前端工具详情相关模块中，保持职责清晰：

- 支持常用 Markdown：标题、段落、列表、粗体、斜体、代码块、行内代码、链接、表格。
- 禁止直接渲染原始 HTML。
- 链接增加安全属性，避免新窗口访问风险。
- 渲染前对文本进行转义，避免 XSS。

## 测试

新增或扩展前端测试：

- 工具编辑页源码应包含 `documentation_markdown` 的读取和保存逻辑。
- 工具详情页源码应包含介绍按钮、弹窗、Markdown 渲染入口。
- Markdown 渲染函数应转义 HTML，并正确渲染基础 Markdown。
- 详情页兜底文档应能从 `input_schema`、`output_schema` 和 `output_globs` 生成。

## 原则应用

- KISS：复用现有版本配置，不新增数据库表和接口。
- YAGNI：先实现单份当前版本介绍，不做多文档管理、草稿发布流和富文本编辑器。
- DRY：参数和输出说明从现有 schema 派生，不在多个位置重复维护。
- SOLID：Markdown 渲染和兜底文档生成抽到独立模块，页面只负责状态和交互。
