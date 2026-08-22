# 平台文档索引

## 1. 当前基线文档

### 产品与需求

- [平台需求说明书](./product/01-平台需求说明书.md)
- [平台功能模块说明书](./product/02-平台功能模块说明书.md)

### 架构与领域设计

- [平台总体架构](./architecture/01-平台总体架构.md)
- [核心领域设计](./architecture/02-核心领域设计.md)
- [部署与计算资源架构](./architecture/03-部署与计算资源架构.md)
- [标准 Artifact 类型设计](./architecture/04-标准Artifact类型设计.md)
- [Tool Contract v2 规范](./architecture/05-ToolContract-v2规范.md)
- [Workflow Binding Resolver 设计](./architecture/06-Workflow-Binding-Resolver设计.md)
- [Remote API 自注册协议](./architecture/07-Remote-API自注册协议.md)
- [Drug Discovery 工具模板规范](./architecture/08-Drug-Discovery工具模板规范.md)
- [K8s / Slurm Executor Adapter 设计](./architecture/09-K8s-Slurm-Executor-Adapter设计.md)
- [前端信息架构与交互设计](./architecture/10-前端信息架构与交互设计.md)

### 验收与测试

- [验收流程与测试场景](./product/03-验收流程与测试场景.md)

### 治理路线

- [平台架构治理路线图](./roadmap/01-平台架构治理路线图.md)

## 2. 文档使用原则

后续需求、功能和代码改造应先判断归属：

1. 是产品目标或用户场景，更新需求文档。
2. 是模块能力或页面能力，更新功能模块说明书。
3. 是系统分层和服务关系，更新总体架构。
4. 是 Project、Artifact、Tool、Task、Workflow、Agent 等领域对象，更新核心领域设计。
5. 是部署、执行器、队列、资源和集群，更新部署与计算资源架构。
6. 是数据输入输出标准，更新标准 Artifact 类型设计。
7. 是工具接入和模型交付，更新 Tool Contract v2 规范。
8. 是工作流自动绑定和输入解析，更新 Workflow Binding Resolver 设计。
9. 是远端模型服务自注册，更新 Remote API 自注册协议。
10. 是药物研发工具类别、模板和接入要求，更新 Drug Discovery 工具模板规范。
11. 是 K8s、Slurm、SSH、Docker 等重计算执行细节，更新 Executor Adapter 设计。
12. 是工作流工作台、工具库、节点面板和可视化交互，更新前端信息架构与交互设计。
13. 是端到端验收、E2E 或发布前检查，更新验收流程与测试场景。

## 3. 历史文档关系

`docs/design`、`docs/plans`、`docs/guides` 中保留历史设计、实施计划和操作指南。新开发优先以本索引中的基线文档为准；历史文档可作为参考，但不再作为架构边界的唯一依据。

## 4. 当前重点

近期治理重点：

1. Artifact / Tool / Task 主线统一。
2. 工具独立运行、项目运行、工作流运行的输入模型统一。
3. 工作流基于标准 Artifact 自动绑定。
4. 药物研发工具节点按标准契约补全。
5. Docker / SSH / Remote API / K8s / Slurm 执行器资源画像统一。
6. 前端工作台围绕傻瓜化输入、节点独立运行和 Artifact Renderer 复用收敛。
