# AIDD Offline Deployment Guide

本文档定义企业离线部署的上线边界。平台生产部署以 `deploy/compose/docker-compose.prod.yml` 为基线，控制面服务必须使用 PostgreSQL、Redis 和 MinIO，不允许回退到 SQLite、本地文件存储或内存缓存。

## 基础环境

- 操作系统支持范围包括麒麟、UOS 和标准 Linux 服务器发行版。
- 海光 x86_64 可作为控制面与 CPU 推理节点架构，但模型运行环境必须通过独立 Runtime Env 验证。
- API、Celery Worker、PostgreSQL、Redis、MinIO 通过离线镜像包和固定配置启动。
- 生产容器不得挂载宿主机 Docker Socket，不在运行时安装模型依赖。

## GPU 与 DCU 边界

- NVIDIA GPU 仅在对应 Tool Package 变体完成镜像 digest、驱动版本、输入输出 hash 和 golden smoke 记录后声明可用。
- 海光 DCU 必须在海光 x86_64 + 麒麟/UOS + DCU 真机上完成同一 golden smoke，不能用 NVIDIA GPU、CPU 或静态校验替代。
- 未完成 DCU 真机验证的工具状态必须标记为 `adapted_pending_hardware_validation`。
- DCU 验证记录必须包含设备型号、DTK/ROCm 版本、驱动版本、镜像 digest、任务日志和失败处理记录。

## 离线交付包

- 平台镜像：frontend、backend、celery-worker、celery-worker-heavy、celery-worker-gpu。
- 有状态服务：PostgreSQL、Redis、MinIO，均需健康检查和持久化卷。
- 模型包：Tool Package v2 manifest、Runtime Env、权重清单、`platform_run.sh` 和 `result.v2` 输出收敛测试。
- 验收材料：部署配置、初始化脚本、管理员账号交接记录、模型 smoke test 和 Artifact 校验报告。

## 上线判定

离线环境上线只证明平台控制面、任务调度、对象存储、数据库和已验证 Runtime Env 可运行。任何没有完成对应硬件 golden smoke 的模型，不得在页面、文档或验收报告中声明该硬件已正式支持。
