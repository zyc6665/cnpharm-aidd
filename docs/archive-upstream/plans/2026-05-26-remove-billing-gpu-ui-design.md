# 删除充值与 GPU 管理展示设计

## 目标

在保留现有登录体系的前提下，移除平台中的充值/会员/积分中心展示入口，以及所有面向用户和管理员的 GPU 管理展示入口，让平台对外聚焦为“登录 + 工具 + 任务”的使用链路。

## 范围

- 保留：
  - 登录、注册、找回密码
  - 工具列表、工具详情、任务创建、任务列表/详情
  - 管理后台基础能力
- 删除展示：
  - `/credits` 路由与充值/会员/积分中心入口
  - 个人中心中的会员升级、积分详情入口
  - 后台系统页中的积分设置、GPU 信息展示
  - 后台仪表板中的 GPU 使用率/显存展示
  - 工具列表、工具详情中的 GPU 标签与 GPU 要求卡片
  - 工具创建/编辑页面中的 GPU 配置项
- 不删除底层：
  - 数据库中的积分/GPU 字段
  - 任务执行时的 GPU 队列与底层模块
  - 已有后端认证体系

## 方案

采用“产品层收口”方案：

1. 前端删除充值和 GPU 管理的所有可见入口与展示文案。
2. 前端保留为兼容运行所需的最小状态字段，不做高风险领域清洗。
3. 后端不做结构性删除，仅保持当前未暴露的充值接口继续不暴露。

## 影响面

### 前端

- 路由：
  - `frontend/src/router/index.ts`
- 布局与用户中心：
  - `frontend/src/views/user/index.vue`
  - `frontend/src/views/user/Profile.vue`
- 后台页面：
  - `frontend/src/views/admin/System.vue`
  - `frontend/src/views/admin/Dashboard.vue`
  - `frontend/src/views/admin/Tools.vue`
- 工具页面：
  - `frontend/src/views/tools/List.vue`
  - `frontend/src/views/tools/Detail.vue`
  - `frontend/src/views/tools/Create.vue`
- Store 暴露：
  - `frontend/src/stores/index.ts`

### 后端

- 认证、工具、任务 API 保持不变。
- 当前 `v1.2` 下充值/会员接口未挂载，维持现状。

## 风险控制

- 不删除底层 GPU/积分字段，避免影响旧数据与任务调度。
- 工具创建/编辑页面只删除可见 GPU 表单项，保留内部字段装载逻辑，避免编辑旧工具时意外重置。
- 通过静态表面测试验证关键页面不再暴露充值与 GPU 管理入口。

## 验证标准

- 前端不再存在 `/credits` 路由。
- 用户中心与个人资料页不再出现充值、会员升级、积分详情入口。
- 后台系统页与仪表板不再展示积分设置、GPU 统计。
- 工具列表、详情、创建/编辑页不再暴露 GPU 相关 UI。
- 前端构建通过。
- 后端健康检查与核心工具/任务接口保持可用。
