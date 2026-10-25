# 首页平台模型与 CPUPDB 介绍区块设计

## 目标

将首页当前的“平台特性”区块替换为一个更有解释力的双栏叙事区块，用于回答两个核心问题：

- `CPUModel 当前平台模型是什么`
- `CPUPDB 在平台中提供什么价值`

这次改动不是简单换文案，而是同步重做信息结构与视觉样式，让这一段从“通用卖点卡片”升级为“平台认知说明区”。

## 背景

当前首页 [frontend/src/views/home/index.vue](/data/zhouyc/cpumodel_sciminer/frontend/src/views/home/index.vue) 的 “Features Section” 使用 4 张等宽卡片来呈现：

- GPU 加速
- 云端处理
- API 集成
- 数据安全

这个结构存在两个问题：

### 1. 与上文内容重复且层级偏浅

首页前面已经有：

- Hero：告诉用户这是一个什么平台
- AIDD 流程段：告诉用户平台覆盖哪些研究步骤

再接一个“平台特性”网格，信息会停留在通用 SaaS 卖点层，无法继续深化“平台是什么”。

### 2. 无法承载 `CPUModel + CPUPDB` 的关系说明

用户这次的目标不是再列一组卖点，而是要让首页讲明白：

- CPUModel 作为工作台与工具层的作用
- CPUPDB 作为结构与口袋数据底座的作用

这类内容更适合叙事式布局，而不是功能卡片网格。

## CPUPDB 公开信息依据

为了避免首页文案失真，本次 `CPUPDB` 的介绍以其官网公开页面为依据。

### 官网首页

CPUPDB 官网将自己描述为一个整合：

- `静态蛋白结构`
- `分子动力学模拟`
- `深度学习模型`

的综合数据库/平台，用于探索多构象状态下的蛋白-配体结合口袋与相关分析。

来源：

- https://www.cpupdb.com/

### 帮助页

帮助页展示了其核心使用路径与模块，包括：

- `Start`
- `Explore`
- `Dynamics`
- `Detail`

并明确强调了蛋白结构、结合口袋、动力学和相互作用分析的多维浏览能力。帮助页当前可见更新时间为 `2025-06`。

来源：

- https://www.cpupdb.com/help.html

本次首页文案会以这些公开描述为边界，不扩写未经公开说明的能力。

## 核心设计决策

### 1. 用双栏叙事甲板替换四卡网格

新结构不再保留 4 张特性卡片，而是改为：

- 一个总标题区
- 一个双栏叙事甲板

左栏讲 `CPUModel`

右栏讲 `CPUPDB`

这样做的原因：

- 可以自然承接 Hero 与 AIDD 流程段
- 能把“平台操作层”和“数据底座层”分开讲清
- 视觉上更高级，也更符合首页当前位置的重要性

### 2. 文案采用产品能力导向，而非底层技术导向

用户已明确偏好 `产品能力导向`。

因此首页这段不会深入讲模型推理机制、框架栈或算法细节，而是聚焦：

- 这个平台适合什么研究路径
- 使用者在这里能完成什么工作
- CPUPDB 如何作为平台的结构与口袋信息支撑

### 3. 保持 `CPUModel` 与 `CPUPDB` 的关系为“协同”，不是“强绑定”

文案上不把 CPUPDB 写成“唯一数据来源”，而是表述为：

- `重要结构与口袋数据底座之一`

这样更稳妥，也避免以后平台引入其他数据库时首页文案失真。

### 4. 行动按钮分工明确

左栏 CTA：

- 跳转 `/workflow`
- 作用是把用户带入 CPUModel 的工作台主路径

右栏 CTA：

- 新标签页打开 `https://www.cpupdb.com`
- 辅助链接可选指向 `https://www.cpupdb.com/help.html`

这样用户不会把平台内部路径和外部数据库入口混淆。

## 信息结构

### 区块标题

- 标题：`平台模型与数据底座`
- 副标题：解释 CPUModel 负责工作台与工具协同，CPUPDB 提供结构与口袋数据支撑

### 左栏：CPUModel

#### 顶部标签

- `Platform Model`

#### 主标题

- `CPUModel 工作台`

#### 定位句

- CPUModel 是一个面向 AIDD 流程的计算工作台，而不是零散工具集合

#### 三个能力点

1. 按研究分组组织工具与流程路径
2. 在任务之间复用历史产物继续计算
3. 串联口袋识别、筛选、对接与性质评估

#### 动作

- 主按钮：`进入工具工作台`

### 右栏：CPUPDB

#### 顶部标签

- `Pocket Data Foundation`

#### 主标题

- `CPUPDB`

#### 定位句

- CPUPDB 是平台的重要结构与口袋数据底座之一，面向蛋白-配体口袋、多构象状态与相互作用分析

#### 三个能力点

1. 覆盖蛋白结构、配体、口袋与结合位点信息
2. 引入动力学数据，用于观察构象变化与隐蔽口袋
3. 支持从检索、Explore、Dynamics 到 Detail 的连续分析

#### 动作

- 次按钮：`访问 CPUPDB`
- 可选轻链接：`查看帮助文档`

## 视觉设计

### 总体方向

使用一个新的 `双栏叙事甲板` 代替等宽网格，风格上延续首页已有的深空科研感，但降低 Hero 那种高对比冲击，转为更精致、更信息化的中段说明区。

### 外层容器

- 深蓝到青金的低对比渐变背景
- 边缘有轻微高光边框
- 背后加入很淡的分子节点/网格纹理

### 双栏卡面

- 两栏各自为半透明亮面板
- 高度一致
- 中间有细分隔线或脉冲式连接装饰

### 内容细节

- 顶部标签采用小号单色胶囊
- 主标题与定位句拉开明显层级
- 三个能力点做成编号能力条，不做旧版那种单独图标大卡
- 按钮风格：
  - 左栏主按钮保持金色主行动风格
  - 右栏按钮做次级亮边按钮

### 响应式

- 桌面端双栏并排
- 平板与手机端改为上下堆叠
- 保证标题、副标题与能力条在窄屏下仍然清晰，不出现过长横向拥挤

## 代码级影响范围

### 主要改动

- [frontend/src/views/home/index.vue](/data/zhouyc/cpumodel_sciminer/frontend/src/views/home/index.vue)
  - 替换旧 Features Section 模板
  - 删除旧 `features` 图标配置
  - 新增双栏介绍区所需数据结构

### 文案改动

- [frontend/src/locales/zh-CN/index.ts](/data/zhouyc/cpumodel_sciminer/frontend/src/locales/zh-CN/index.ts)
- [frontend/src/locales/en-US/index.ts](/data/zhouyc/cpumodel_sciminer/frontend/src/locales/en-US/index.ts)

需要删除或废弃旧的：

- `home.features.items.gpu`
- `home.features.items.cloud`
- `home.features.items.api`
- `home.features.items.security`

改为新的：

- `home.foundation.title`
- `home.foundation.subtitle`
- `home.foundation.platform.*`
- `home.foundation.cpupdb.*`

## 测试策略

### 1. 首页表面测试

新增或扩展前端表面测试，断言：

- 首页不再渲染旧 `home.features.items.cloud/api/security` 文案结构
- 新增 `home.foundation` 文案键
- 首页存在 `CPUModel` 与 `CPUPDB` 双栏区块
- 存在 CPUPDB 外链并指向正确官网地址

### 2. 回归验证

至少运行：

- 首页相关表面测试
- `npm run build`

## 非目标

本次不做：

- Hero 区重写
- AIDD 流程区改版
- CPUPDB 深度页面内嵌
- 新的数据 API 接入
- 全站主题重构
