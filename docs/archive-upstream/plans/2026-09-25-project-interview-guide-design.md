# 项目学习与面试指南文档设计

## 目标

新增一篇中文项目文档，帮助求职者理解科学计算工具管理平台的业务背景、系统架构、技术实现、工程亮点和现实边界，并将这些内容转换为可用于面试和简历的表达。

## 内容设计

文档按以下顺序组织：

1. 一分钟项目介绍和业务问题。
2. 总体架构、核心领域对象和一次任务执行链路。
3. 后端、前端、数据、异步任务、存储、资源调度和安全技术栈。
4. Standard Artifact、Tool Contract、Run Preparation、Executor Adapter、Workflow 等关键设计。
5. 已实现能力、架构规划与证据路径的边界说明。
6. 项目亮点、痛点、可改进方向和面试高频问题。
7. 简历项目描述、学习路线和常用代码入口。

## 事实边界

内容以 `README.md`、`PRODUCT.md`、`CONTEXT.md`、`docs/architecture`、`docs/product` 和当前代码为依据。规划中的 Candidate/Assay/DMTA 能力标注为路线图，不作为已上线功能；生产部署以 PostgreSQL、Redis、MinIO、Celery 为准，开发模式说明 SQLite、本地文件、内存缓存和 direct 执行的限制。

## 变更范围

只新增文档，不修改业务代码、配置、测试或用户现有未提交改动。
