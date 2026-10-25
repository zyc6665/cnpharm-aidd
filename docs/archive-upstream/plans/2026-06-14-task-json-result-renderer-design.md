# 任务 JSON 结果列表渲染器设计

## 目标

任务详情页和工作流结果面板应把结构化 `output_data` 渲染成可扫描的分组列表，而不是把对象直接显示为原始 JSON 代码块。该能力必须通用，适用于 MSIGN 以及后续返回类似结构的新工具。

## 方案

新增一个通用 JSON 结果渲染组件，接收任意 `unknown` 数据并递归渲染：

- 标量值显示为紧凑键值行。
- 普通对象显示为分组列表。
- 对象数组显示为重复列表项。
- 深层对象继续递归渲染。
- 数字做有限精度格式化，保留整数原样。
- `snake_case`、`camelCase`、短横线字段名转为可读标题。
- 保留可折叠的原始 JSON，方便排查和复制。

## 组件边界

- `frontend/src/components/tasks/json-result-renderer.ts`：纯函数，负责标签、数值、摘要和节点分类。
- `frontend/src/components/tasks/JsonResultRenderer.vue`：展示组件，负责递归 UI。
- `frontend/src/components/tasks/TaskOutputSummary.vue`：继续负责输出区组合，把 `output_data` 交给通用渲染器。

## 数据流

`TaskOutputSummary` 从 `task.output_data` 取值。如果是顶层对象，按字段分组渲染；如果是数组或标量，也直接传给通用渲染器显示。输出文件列表逻辑保持不变。

## 错误处理

渲染器必须处理 `null`、空数组、空对象、未知嵌套结构和不可序列化边界值。遇到无法细分的数据时回退成字符串展示，不抛出运行时错误。

## 测试

新增前端测试覆盖：

- 字段名格式化。
- 数值精度格式化。
- MSIGN 风格数据生成分组和数组列表节点。
- `TaskOutputSummary` 接入 `JsonResultRenderer`，且不再对对象直接 `JSON.stringify`。
