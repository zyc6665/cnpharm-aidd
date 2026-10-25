# 工具 API 路由拆分设计

## 目标

完成技术债清单 `2.2.1`，将 `backend/app/api/v1/tools.py` 中剩余的公开查询、管理员写操作、版本管理与共享辅助逻辑拆入独立模块，同时保持现有 URL、权限依赖、响应结构和数据库事务语义不变。

## 方案选择

采用“共享辅助模块 + 三个职责路由 + 兼容聚合模块”方案：

- `tool_route_utils.py`：序列化、工具加载、分类校验、契约构建、事务冲突转换与导入服务。
- `tools_public.py`：工具列表、公开工作台、分类/标签读取、示例、契约、详情与收藏。
- `tools_admin.py`：工具导入、创建、更新、删除、发布与标签创建。
- `tool_versions.py`：版本列表与版本创建。
- `tools.py`：仅聚合子路由，保留 `tools.router` 既有导入入口。

没有采用直接修改 `api/v1/__init__.py` 分别挂载所有路由的方案，因为继续保留 `tools.router` 可以降低外部测试、扩展代码和应用初始化层的兼容风险。也不引入额外 service 层；本次只移动已有路由职责，避免扩大范围。

## 路由与数据流

所有子路由使用无前缀 `APIRouter`，由 `tools.py` 按静态优先顺序聚合，再由 `api/v1/__init__.py` 继续以 `/tools` 前缀挂载。静态路径（如 `/import-config`、`/tags`、`/workbench-groups`）必须在 `/{tool_id}` 动态路由之前注册，防止路由误匹配。

共享辅助函数只能依赖模型、schema 和 service，不反向导入任何路由模块。三个路由模块可依赖共享辅助模块，彼此之间不互相导入，从而避免循环依赖。

## 兼容与错误处理

- 保持 `tools.router`、现有端点 URL、HTTP 方法和依赖注入不变。
- 保持 `NotFoundException`、`ForbiddenException`、`ConflictException` 与 `ValidationException` 行为不变。
- 保持收藏统计、导入后 capability 同步、版本激活和唯一约束冲突处理不变。
- 保留现有响应包装 `success_response` 与 `paginated_response`。

## 测试策略

先添加模块布局失败测试，要求新模块存在、兼容聚合模块不再定义业务端点，并验证关键路由仍注册在原路径。随后逐批迁移：共享辅助函数、公开路由、管理路由、版本路由。每批运行相应工具 API 聚焦测试并提交，最后运行完整后端测试、前端测试与前端生产构建。
