# 平台文档索引

## 1. 当前基线文档

### 产品与需求

- [平台需求说明书](./product/01-平台需求说明书.md)
- [平台功能模块说明书](./product/02-平台功能模块说明书.md)

### 企业交付文档

- [需求规格说明书](./delivery/01-企业交付需求规格说明书.md)
- [系统设计说明书](./delivery/02-企业交付系统设计说明书.md)
- [部署运维说明书](./delivery/03-企业交付部署运维说明书.md)

### 架构与领域设计

- [平台总体架构](./architecture/01-平台总体架构.md)
- [核心领域设计](./architecture/02-核心领域设计.md)
- [部署与计算资源架构](./architecture/03-部署与计算资源架构.md)
- [标准 Artifact 类型设计](./architecture/04-标准Artifact类型设计.md)
- [Tool Contract v2 规范](./architecture/05-ToolContract-v2规范.md)
- [Run Preparation 与 Binding Resolver 设计](./architecture/06-Workflow-Binding-Resolver设计.md)
- [Remote API 自注册协议](./architecture/07-Remote-API自注册协议.md)
- [Drug Discovery 工具模板规范](./architecture/08-Drug-Discovery工具模板规范.md)
- [K8s / Slurm Executor Adapter 设计](./architecture/09-K8s-Slurm-Executor-Adapter设计.md)
- [前端信息架构与交互设计](./architecture/10-前端信息架构与交互设计.md)
- [软件工程架构治理规范](./architecture/11-软件工程架构治理规范.md)
- [模块边界与迁移计划](./architecture/12-模块边界与迁移计划.md)
- [标准 Artifact 驱动边界设计](./architecture/13-标准Artifact驱动边界设计.md)
- [平台功能地基设计](./architecture/14-平台功能地基设计.md)
- [现有平台改造完善方案](./architecture/15-现有平台改造完善方案.md)
- [药研数据与科学结果规范](./architecture/16-药研数据与科学结果规范.md)
- [模型卡与科学验证发布门禁规范](./architecture/17-模型卡与科学验证发布门禁规范.md)

### 验收与测试

- [验收流程与测试场景](./product/03-验收流程与测试场景.md)

### 治理路线

- [平台架构治理路线图](./roadmap/01-平台架构治理路线图.md)
- [DMTA 实验反馈闭环路线图](./roadmap/02-DMTA实验反馈闭环路线图.md)

### 团队协作与开发规范

- [团队协作开发规范与教程](./development/01-团队协作开发规范与教程.md)

## 2. 文档使用原则

后续需求、功能和代码改造应先判断归属：

1. 是产品目标或用户场景，更新需求文档。
2. 是模块能力或页面能力，更新功能模块说明书。
3. 是系统分层和服务关系，更新总体架构。
4. 是 Project、Artifact、Tool、Task、Workflow、Agent 等领域对象，更新核心领域设计。
5. 是部署、执行器、队列、资源和集群，更新部署与计算资源架构。
6. 是数据输入输出标准，更新标准 Artifact 类型设计。
7. 是工具接入和模型交付，更新 Tool Contract v2 规范。
8. 是工作流自动绑定、输入解析和运行准备，更新 Run Preparation 与 Binding Resolver 设计。
9. 是远端模型服务自注册，更新 Remote API 自注册协议。
10. 是药物研发工具类别、模板和接入要求，更新 Drug Discovery 工具模板规范。
11. 是 K8s、Slurm、SSH、Docker 等重计算执行细节，更新 Executor Adapter 设计。
12. 是工作流工作台、工具库、节点面板和可视化交互，更新前端信息架构与交互设计。
13. 是端到端验收、E2E 或发布前检查，更新验收流程与测试场景。
14. 是模块边界、架构规则、依赖方向和重构治理，更新软件工程架构治理规范。
15. 是从原型堆积迁移到工程化模块，更新模块边界与迁移计划。
16. 是新工具扩展后工作流仍可运行的 Artifact 边界、状态机和预检规则，更新标准 Artifact 驱动边界设计。
17. 是平台功能地基、核心能力依赖顺序和新工具扩展主线，更新平台功能地基设计。
18. 是现有原型是否开始重构、先改哪些模块、如何验收和回滚，更新现有平台改造完善方案。
19. 是团队协作、模块分工、分支、PR、合并、发布和新人教程，更新团队协作开发规范与教程。
20. 是企业交付、客户评审、验收归档或正式投标材料，更新企业交付文档。
21. 是分子、预测、评分、实验回写和科学证据语义，更新药研数据与科学结果规范。
22. 是模型适用范围、性能证据、科学发布门禁或版本废弃，更新模型卡与科学验证发布门禁规范。
23. 是从候选设计到实验反馈的 DMTA 产品阶段规划，更新 DMTA 实验反馈闭环路线图。

## 3. 历史文档关系

当前基线以本索引列出的文档为准。旧 `docs/design`、`docs/frontend`、`docs/guides`、`docs/archive` 和根目录零散历史报告不再作为当前架构边界的依据；如需追溯历史内容，应通过 Git 历史、归档 tag 或单独归档分支查看。

`docs/plans` 可保留阶段性实施计划，但计划内容不能覆盖本索引中的需求、架构、部署和开发规范基线。

## 4. 当前重点

近期治理重点：

1. Artifact / Tool / Task 主线统一。
2. 工具独立运行、项目运行、工作流运行的输入模型统一。
3. 工作流基于标准 Artifact 自动绑定。
4. 药物研发工具节点按标准契约补全。
5. Docker / SSH / Remote API / K8s / Slurm 执行器资源画像统一。
6. 前端工作台围绕傻瓜化输入、节点独立运行和 Artifact Renderer 复用收敛。
7. Architecture Kernel 的 Interface 先冻结，再按链路迁移旧实现。
8. 标准 Artifact 驱动的边界状态机先定型，再实现 Run Preparation。
9. 平台功能地基按 Artifact Registry、Tool Contract、Result Manifest、Run Preparation、Task Command、Workflow Orchestration 的顺序冻结。
10. 现有平台进入受控改造，不做大爆炸重写，先以两条药物研发验收链路建立回归保护网。
11. 科学结果语义、模型证据等级和评分可比性在 Artifact 与 Tool Contract 层冻结。
12. 在不替代 LIMS/ELN 的边界内，按 DMTA 路线引入实验结果回写和预测-实测复盘。
