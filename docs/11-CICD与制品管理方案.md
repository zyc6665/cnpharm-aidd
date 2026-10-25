# 中国医药 AI 药物研发平台 · CI/CD 与制品管理方案

| 项 | 内容 |
|---|---|
| 文档编号 | DRP-CICD-v1.2 |
| 文档版本 | **v1.2**（2026-10-23 生产级复审补齐；此前 v1.1 于 2026-10-20 架构评审修订，变更明细见 `03A`） |
| 文档状态 | 待评审 |
| 上游依据 | `03-系统架构设计说明书.md`（§4 部署、§6.1 版本矩阵、§8.4 发布策略、§10 离线交付）、`07-模型交付与运行规范.md`（§4 镜像三层体系、§7 模型上线流程）、`09-算力节点与模型运行部署方案.md`（§3 执行后端抽象）、`10-开发规范与编码约定.md`（§10~§12 门禁） |
| 下游消费 | `12-测试计划与测试用例集.md`、`13-部署架构与上线方案.md`（§6 离线包组装）、迭代交付与发版 |
| 核心约束 | **C-1 内网离线**：构建、测试、发布全链路不得依赖公网 |

---

## 0. 本文档要解决的五个问题

1. **离线怎么持续集成** —— 甲方内网无公网，GitHub Actions / 公网 Runner 均不可用，需要一套纯内网的 CI 方案与依赖预热机制。
2. **镜像怎么控体积** —— `07` §4.1 已指出：9 个模型若各自打包 `.venv` 会吃掉 ~35GB 且无法复用；CI 必须强制分层与复用。
3. **DCU 构建怎么办** —— `07` §4.2 明确指出 `torch.cuda.is_available()` 断言在无卡构建机上必然失败，必须在带 DCU 的节点上构建或下沉为运行期 smoke。这是 CI 设计的硬分支。
4. **"新模型接入 ≤ 5 人日"如何被流水线保障** —— DRP-NFR-11 的量化目标，必须由模型包门禁流水线（而非人工）来兜底。
5. **发版和回滚怎么做到分钟级且可追溯** —— 每个制品必须能回答"它由哪个 commit、哪份 lock、哪组版本矩阵产出"。

---

## 1. CI/CD 总体设计

### 1.1 平台选型

| 方案 | 结论 | 理由 |
|---|---|---|
| GitHub Actions / GitLab SaaS | ❌ **不可用** | 甲方内网无法访问公网；即便开发期可用，交付后也无法复现流水线 |
| **GitLab CE（自建，内网）** | ✅ **采用** | 自带 Runner + 容器 Registry 联动 + MR 门禁；离线安装简单（Omnibus 单包）；与 Harbor 同一套 docker 认证 |
| Jenkins | 备选 | 插件生态在离线环境维护成本高（插件依赖公网） |
| 自研脚本 + cron | ❌ 不采用 | 无审计、无并发隔离、无制品追溯 |

> **与"甲方是否已有 CI"的关系**：若甲方内网已有 GitLab/Jenkins，则**流水线定义不变**（本文的 Stage 与门禁是逻辑定义），只替换执行器。所有门禁脚本放在仓库 `tools/` 下，与 CI 平台解耦，可被任何执行器调用。

### 1.2 制品仓库拓扑（全内网）

```
                    ┌──────────────────────────────────────────────┐
                    │  GitLab CE（源码 + MR + CI 调度）             │
                    └───────────────┬──────────────────────────────┘
                                    │ 触发
                    ┌───────────────▼──────────────────────────────┐
                    │  GitLab Runner 池                             │
                    │  ├ runner-app : 通用/前端/契约（无卡）        │
                    │  ├ runner-dcu : 镜像构建 + DCU 冒烟（有卡）   │
                    │  └ runner-perf: 性能压测（可借用弹性卡）      │
                    └───┬───────────┬───────────┬──────────────────┘
                        │ push      │ push      │ 上传
                ┌───────▼──┐  ┌─────▼────┐  ┌───▼─────────┐
                │  Harbor  │  │ devpi /  │  │ MinIO        │
                │  镜像仓库 │  │ Nexus    │  │ 制品/报告    │
                │  项目:    │  │ PyPI 私服 │  │ drp-artifact │
                │ app/calc/ │  │ npm 私服  │  │ drp-report   │
                │ runtime/  │  │ helm repo│  │              │
                │ base/     │  └──────────┘  └──────────────┘
                └──────────┘
```

| 制品类型 | 存储 | 命名空间 / 前缀 | 保留策略 |
|---|---|---|---|
| 应用镜像 | Harbor `drp/app` | `drp-<unit>:<版本>`（**unit = 8 个部署单元**，见下） | 保留最近 50 个 tag + 全部 release tag |
| 计算镜像 L0/L1 | Harbor `drp/base`、`drp/runtime` | `base-dtk:26.04`、`runtime-<族>-dtk26.04-py3.10:<版本>` | **永久保留**（一旦发布不可变） |
| 计算镜像 L2 | Harbor `drp/calc` | `<model>:<modelVer>-<runtimeVer>` | 永久保留（历史任务需拉取旧版本） |
| Python 制品 | devpi / Nexus | `/root/pypi/+simple/`、`/root/drp/` | 永久 |
| npm 制品 | Nexus npm proxy | — | 永久 |
| 前端静态包 | Harbor（打进 nginx 镜像） | `drp/web:<版本>` | 50 个 |
| Helm Chart | Harbor（OCI chart） | `drp/charts/drp-platform:<版本>` | 全部 release |
| 测试报告 / 覆盖率 / SBOM | MinIO `drp-report` | `ci/<pipelineId>/`、`release/<版本>/` | 报告 180 天；release 报告永久 |
| 模型权重包 | MinIO `drp-model-weights` + SHA-256 清单 | `<model>/<version>/` | 永久 |

> **v1.1 补充：应用镜像只有 8 个，不是 12 个**。`03` §3.2.1 将 12 个逻辑模块合并为 8 个部署单元，因此 `drp/app` 下的镜像清单是：`drp-api` / `drp-task-api` / `drp-scheduler` / `drp-mol-index` / `drp-model-registry` / `drp-worker-cpu` / `drp-web` / `drp-gateway`（Ingress 配置包，非自建镜像）。
>
> **注意 `drp-task-api` 与 `drp-scheduler` 虽然镜像不同，但必须使用同一套 DB 迁移版本**——`03` §3.2.2 的四项强一致操作要求二者共用库连接与事务边界。因此两者的 `alembic` 迁移必须**同一流水线同一阶段执行**，不得各自独立升级 schema。

### 1.3 环境与分支对应

| 环境 | 触发条件 | 部署方式 | 数据 | 用途 |
|---|---|---|---|---|
| `dev`（开发共享） | `main` 每次合入 | 自动部署 | 合成数据 | 联调、迭代演示 |
| `staging`（预发） | `release/v*` 分支或手动 | 自动 + 人工确认 | 脱敏样例 + 真实模型 | 验收彩排、性能测试 |
| `prod`（甲方现场） | release tag + 变更单 | **离线介质 + 人工执行** | 真实 | 交付运行 |
| `perf`（性能） | 手动 | 按需 | 生成数据 | 压测（`12` §4） |

> **红线**：任何环境禁止连接公网；`dev/staging` 与 `prod` 之间无网络通路，制品通过介质摆渡（§6）。

---

## 2. 流水线设计（Stage 定义）

### 2.1 应用侧流水线（`services/**`、`packages/**`、`web/**`）

```
S0 预检 ─▶ S1 静态门禁 ─▶ S2 单元测试 ─▶ S3 构建镜像 ─▶ S4 集成/契约 ─▶ S5 安全扫描 ─▶ S6 推送制品 ─▶ S7 部署 dev/staging
```

| Stage | 内容 | 门禁（阻断） | 超时目标 |
|---|---|---|---|
| **S0 预检** | 分支命名校验、commitlint、变更范围探测（受影响服务） | 命名不合规、commit 格式错误 | 1 min |
| **S1 静态门禁** | `ruff format --check`、`ruff check`、`mypy --strict`、`lint-imports`、`uv lock --check` | 任一失败 | 5 min |
| **S2 单元测试** | `pytest -m "not integration"`，`--cov`，覆盖率门槛（`10` §3.6） | 覆盖率低于门槛、任一失败 | 10 min |
| **S3 构建镜像** | Kaniko（无特权）构建，带 SBOM 与 provenance 标签 | 基础镜像非白名单、构建失败 | 10 min |
| **S4 集成/契约** | 起 PG15/Redis7/MinIO/RabbitMQ；跑 `integration` + OpenAPI 契约测试 + 迁移升降验证 | 契约不匹配、迁移降级失败 | 20 min |
| **S5 安全扫描** | Trivy（镜像 CVE，按严重度阈值）、gitleaks、pip-licenses 白名单、外网调用扫描 | 高危 CVE、GPL/AGPL 引入、外网地址 | 10 min |
| **S6 推送制品** | 打 tag（`<分支>-<短SHA>-<序号>`）、推 Harbor、上传报告与 SBOM | 推送失败 | 5 min |
| **S7 部署** | `dev` 自动（Helm atomic upgrade + 健康探针 + smoke）；`staging` 需人工按钮 | 部署后 smoke 失败自动回滚 | 10 min |

**关键实现约定**：

| 编号 | 约定 |
|---|---|
| PL-01 | 使用 Kaniko 而非 Docker-in-Docker（内网不开放特权容器；且 Kaniko 可在非 root 下运行） |
| PL-02 | 镜像标签策略：`<service>:<gitSha8>`（不可变）+ `<service>:<env>-latest`（可变，仅 dev 使用） |
| PL-03 | 先在 S0 计算**受影响服务清单**（基于 `git diff` 路径匹配 + 依赖图），只跑受影响的 S2~S6，避免全量超时 |
| PL-04 | 所有 Stage 必须产出**机器可读结果**（JUnit XML / coverage.xml / trivy.json / sarif），统一归档到 MinIO `ci/<pipelineId>/` |
| PL-05 | 流水线失败必须在 MR 中回贴**具体失败项**（脚本输出截取 + 报告链接），不允许只显示"失败" |
| PL-06 | `main` 上的流水线失败视为 P0，当日必须修复（红主干不可过夜） |
| PL-07 | 缓存：`uv` 缓存与 `web/node_modules` 走 Runner 本地缓存卷（离线，不依赖外部服务） |

### 2.2 计算侧流水线（`compute/models/**`）

> 对应 `07` §7「模型上线流程」的 8 个步骤，此处落成可执行的 4 条独立流水线。

**P-M1 交付包静态门禁（无需 DCU，分钟级）**

| 步骤 | 内容 | 门禁 |
|---|---|---|
| 结构校验 | `manifest.yaml` 是否符合 `07` §2.2 Schema（jsonschema） | 字段缺失/类型错误即失败 |
| 目录校验 | 必选目录 `code/ entrypoint/ io/ sample/` 齐全；禁止自带 `.venv` | 违规即失败 |
| 版本一致性 | `manifest.runtime.frameworks` 必须与 `versions.yaml` 逐项一致 | 不一致即失败 |
| License | `metadata.license` 必填且不在 GPL/AGPL 黑名单（除非标记隔离） | 缺失即失败 |
| 能力映射 | `capabilities[].taskType` 必须属于 `03` §3.3 枚举 | 非法即失败 |
| 资源合理性 | `device.memoryGB` / `maxMinutes` 与 `03` §5.2 资源画像偏差 ≤ ±50% | 超限需人工审批 |

**P-M2 镜像构建（需 DCU 节点）**

```yaml
# 关键：L1 基座镜像必须在 DCU 机器上 docker build（07 §4.2）；没有「Kaniko Pod 申请 1 张 DCU」这条路
# 日常 L2 构建不需 DCU：构建期只做 pip check + import，设备断言下沉为 P-M3 的运行期 smoke
stages:
  - build-l0    # 仅当 base 变更时（DCU 机器上构建）
  - build-l1    # 仅当 runtime 族定义变更时（DCU 机器上构建，缓存命中率 > 90%）
  - build-l2    # 每次模型包变更（Kaniko，无 DCU）
  - verify      # L1：构建期断言 torch 2.7.1 / hip 6.3.26045 / cuda.is_available；L2：仅 pip check + import
```

> **v1.1 修订**：原注释写「Kaniko Pod 申请 1 张 DCU」，与 `07` §4.2 v1.1、`09`、`13` 矛盾（DCU 不进 K8s，没有可申请 DCU 的 Kaniko Pod）。现改为：L0/L1 在 DCU 机器上 `docker build`，L2 走 Kaniko，设备断言下沉到 P-M3 的运行期 smoke。

| 编号 | 约定 |
|---|---|
| MPL-01 | L0/L1 变更需**架构负责人审批**，因为影响全部 9 个模型 |
| MPL-02 | L2 层体积 > 2GB 视为异常，CI 打印层分解（`dive` 离线版）并要求说明 |
| MPL-03 | 镜像 tag 规则：`<model>:<modelVersion>-<runtimeVersion>`，例 `boltz2:2.0.1-r1210`（r = runtime 版本号） |
| MPL-04 | 镜像一旦推送即**不可变**；禁止重复推送同 tag（Harbor 开启不可变 tag 规则） |

**P-M3 冒烟与 DCU 压力验证（需 DCU 节点）**

| 阶段 | 内容 | 通过标准 |
|---|---|---|
| 冒烟 | `sample/input` → 容器执行 → 与 `sample/expected` 比对 | 关键字段数值偏差 ≤ 阈值（模型自带 `expected.json` 声明容差） |
| 单卡基准 | 记录 wall / 峰值显存 / `hy-smi` 采样 | 与 `manifest.resources.steadyStateSecondsPerItem` 偏差 ≤ 30%；冷启单独与 `coldBootSeconds` 比对（两者不得混算，见 `03` §5.2.1） |
| 8 卡并发 | 同时起 8 个容器（跨两台机器，`09` §5） | 成功率 100%（重试 ≤ 1 次） |
| soak | 连续 20 轮（可夜间执行） | 无 OOM、无 NaN、显存无泄漏（末轮峰值 ≤ 首轮 1.1×） |
| 取消验证 | 运行中发取消信号 | 60s 内优雅退出，部分产物保留（`03` §3.4） |

> **DCU 资源节流**：P-M3 使用 `runner-perf` 池，并受 `09` §5.3 弹性借用规则约束；同一时间只允许 1 个模型占用压力资源，避免与业务任务争抢。

**P-M4 注册与灰度**

| 步骤 | 内容 |
|---|---|
| 注册 | 写入 `model_registry`（`04` §11.1），`version = PUBLISHED`，绑定 `image_ref` + `manifest` 摘要（sha256） |
| 灰度 | 阶段 1 仅管理员可见 → 阶段 2 试点项目 → 阶段 3 全量；每阶段最少 3 个真实任务成功 |
| 回滚 | 将 `model_registry` 指向上一版本即可（镜像不删）；已提交任务仍绑定旧版本（`07` §7 版本纪律） |
| 下线 | `version = DEPRECATED`：禁止新任务，历史任务可查可用 |

### 2.3 前端与部署制品流水线

| 制品 | 流水线要点 |
|---|---|
| `drp/web` 镜像 | `vite build` → 静态资源打包进 nginx 镜像；构建产物带 `BUILD_ID` 注入到页面，用于确认版本 |
| Helm Chart | `helm lint` + `helm template --validate`（离线 kubeconform）+ `helm package` 推 OCI |
| 数据库迁移包 | 与 `drp-migrate` 镜像一并产出；版本号与 chart 版本对齐 |
| 离线安装包 | 见 §6，由发布流水线自动组装并生成校验清单 |

---

## 3. 分支、环境与发布策略

### 3.1 环境提升路径

```
feat/fix ──MR──▶ main ──▶ dev（自动）
                  │
                  └──▶ release/v1.2.0 ──▶ staging（自动 + 确认）──▶ tag v1.2.0 ──▶ 离线包 ──▶ prod（人工）
```

### 3.2 版本号规则（语义化版本）

| 制品 | 版本规则 | 示例 |
|---|---|---|
| 平台（整体） | `v<主>.<次>.<修>`，主版本仅在破坏性变更时递增 | `v1.2.0` |
| 服务镜像 | 与平台版本一致（同一 release 内所有服务版本号对齐，便于运维排障） | `drp-task:1.2.0` |
| runtime 镜像 | `r<序号>`，每次 L1 内依赖变更递增 | `runtime-dgl-dtk26.04-py3.10:r3` |
| 模型镜像 | `<modelVersion>-r<runtime号>` | `boltz2:2.0.1-r3` |
| Helm Chart | 与平台版本一致 | `drp-platform-1.2.0.tgz` |

> **决策理由**：服务版本对齐平台版本，牺牲一点粒度换取"现场看到的每一个 tag 都能反查到同一份 release 说明与同一个离线包"，这在离线交付与验收场景下价值远大于粒度收益。

### 3.3 发布策略（对应 `03` §8.4）

| 组件 | 策略 | 说明 |
|---|---|---|
| 无状态业务服务 | 滚动更新（`maxSurge=1, maxUnavailable=0`）+ 就绪探针 | 保证 ≤ 3s 响应（`03` §3.5） |
| 网关/Ingress | 金丝雀（5% → 25% → 100%） | 观察 5xx 与 P95 |
| 数据库迁移 | 先迁移后发应用（三步走，`10` §4.3） | 迁移必须向后兼容 |
| 模型服务（RESIDENT） | 蓝绿（新副本就绪 → 切流量 → 旧副本保留 24h） | 冷启动 110s，不能滚动 |
| 模型任务（BATCH） | 版本绑定，不切换历史 | 新任务用新版本，旧任务继续用旧镜像 |

---

## 4. 质量门禁总表（合并阻断项）

| 编号 | 门禁 | 阈值 | 适用 |
|---|---|---|---|
| G-01 | `ruff format --check` / `ruff check` | 零问题 | 全仓 Python |
| G-02 | `mypy --strict` | 零 error | 全仓 Python |
| G-03 | `lint-imports`（分层依赖） | 零违反 | `services/**` |
| G-04 | 单元测试 | 全通过 | 全仓 |
| G-05 | 覆盖率 | 全仓 ≥ 75%；`domain` ≥ 90%；`runner` ≥ 80% | 全仓 |
| G-06 | 集成测试 | 全通过 | 涉及 DB/中间件变更 |
| G-07 | OpenAPI 契约 | 与 `05` 无破坏性偏差 | 接口变更 |
| G-08 | 迁移升降 | `upgrade head` + `downgrade base` 成功 | 涉及 `migrations/` |
| G-09 | 前端类型与构建 | `tsc --noEmit` + `vite build` 通过 | `web/**` |
| G-10 | 镜像高危 CVE | HIGH/CRITICAL = 0（除白名单） | 全部镜像 |
| G-11 | 许可证白名单 | 无 GPL/AGPL（隔离目录除外） | 全仓 |
| G-12 | 外网调用扫描 | 零命中（`03` §10 红线） | 全仓 + 镜像 |
| G-13 | 禁止 import 扫描 | 零命中（`10` 附录 A） | `services/**` |
| G-14 | 密钥扫描 | 零命中 | 全仓 |
| G-15 | 模型包静态门禁 | P-M1 全通过 | `compute/models/**` |
| G-16 | 模型冒烟（DCU） | sample 比对通过 | 模型镜像变更 |
| G-17 | MR 审批 | ≥ 1 人（敏感路径 2 人） | 全部 MR |

> **白名单机制**：G-10/G-11 允许带**到期日**的白名单条目（`tools/whitelist/cve.yaml`、`license.yaml`），每条必须写明理由与责任人；到期自动重新阻断。禁止永久白名单。

---

## 5. 镜像分层与构建缓存策略

### 5.1 三层体系在 CI 中的落地（对应 `07` §4.1）

| 层 | 变更频率 | CI 触发 | 缓存策略 | 审批 |
|---|---|---|---|---|
| L0 `base-dtk` | 极低（DTK 升级时） | 手动 | Harbor 拉取 + Kaniko 层缓存 | 必须审批 |
| L1 `runtime-*` | 低（依赖族变更） | 手动/定时 | Kaniko `--cache-repo` 指向 Harbor | 必须审批 |
| L2 `model` | 高（每次模型包提交） | 自动 | 命中 L1 缓存，实际构建 < 3 min | 自动 |

**体积预算**：L1 每个 ≤ 6GB（`07` §4.1 实测 `.venv-dcu` 3.9G 的上限控制），L2 ≤ 2GB，超出即 CI 报警并记录到构建报告。

### 5.2 依赖预热与离线镜像源

| 依赖源 | 预热方式 | 更新流程 |
|---|---|---|
| PyPI | 内网 devpi 镜像（首次由装机时联网导入白名单包） | 新依赖提交 MR 时附带 `tools/deps/proxies.yaml` 变更，由平台组从外网取包后导入 |
| npm | Nexus npm proxy（同上） | 同上 |
| 基础镜像 | Harbor `drp/base`（OS、Python、Node、nginx 基础镜像） | 平台组定期批量同步 |
| Helm Charts | Harbor OCI 仓库 | 与平台版本同步 |

> **红线检查**：S5 阶段对**镜像内容**（不只是源码）执行外网扫描：搜索 `http://`、`https://`（白名单为内网域名与 `LICENSE` 文件中的说明性链接）、`pypi.org`、`registry.npmjs.org` 等特征串。

---

## 6. 离线交付制品包（对应 `03` §10）

### 6.1 发布包结构

```
drp-release-v1.2.0/
├── MANIFEST.yaml                 # 包清单：所有制品 + sha256 + 大小
├── SHA256SUMS                    # 全部文件校验（含 MANIFEST 自身由签名覆盖）
├── SHA256SUMS.sig                # GPG 签名（我方交付私钥签署）
├── images/
│   ├── drp-app-v1.2.0.tar        # 全部业务服务 + web + 迁移镜像
│   ├── drp-runtime-v1.2.0.tar    # L0/L1 镜像
│   └── drp-calc-v1.2.0.tar       # L2 模型镜像
├── charts/
│   └── drp-platform-1.2.0.tgz
├── models/
│   ├── weights/
│   │   └── <model>/<version>/*.safetensors
│   └── WEIGHTS-SHA256.txt
├── deps/
│   ├── pypi-wheels/              # 业务服务运行期依赖
│   └── npm-packages/
├── db/
│   ├── schema.sql                # 初始化 DDL（等价于 alembic head）
│   └── seed.sql                  # 预置数据（角色、示例工作流模板）
├── scripts/
│   ├── install.sh                # 首次安装（含预检、导入、初始化）
│   ├── upgrade.sh                # 升级（含备份点、迁移、回滚开关）
│   ├── rollback.sh               # 回滚到上一版本
│   └── preflight.sh              # 环境检查（内核、驱动、磁盘、端口、时钟）
└── docs/
    ├── release-notes.md
    └── 部署与上线方案.md
```

### 6.2 包生成与验收

| 步骤 | 内容 | 门禁 |
|---|---|---|
| 1 | 从 release tag 拉取，`make deterministic-build`（固定 `SOURCE_DATE_EPOCH`，产出可复现镜像） | 两次构建 digest 一致 |
| 2 | 收集镜像、chart、权重、依赖 wheels | — |
| 3 | 生成 `MANIFEST.yaml` 与 `SHA256SUMS`，GPG 签名 | 签名校验通过 |
| 4 | **空环境演练**：在隔离测试集群执行 `install.sh` → 冒烟 → `upgrade.sh` → `rollback.sh` | 全流程成功，耗时记录 |
| 5 | 生成发布说明（变更清单、已知问题、升级注意事项、数据库变更说明） | 至少 1 人复核 |
| 6 | 介质摆渡（加密移动介质/甲方指定通道） | 双人签收，sha256 现场校验 |

> **演练是硬门禁**：未在空环境完整跑通「安装 → 升级 → 回滚」的包，不得交付现场。该演练结果同时作为后续《部署架构与上线方案》（编号 13，第三批规划）与验收报告的证据。

---

## 7. 版本矩阵与依赖治理

### 7.1 `versions.yaml`（唯一真源）

```yaml
# 由 CI 强制校验：业务依赖、runtime 镜像、模型 manifest 三处必须一致
platform:
  python: "3.10"
  node: "20"
compute:
  dtk: "26.04"
  hyhal: "/opt/hyhal"
  torch: "2.7.1"
  hip: "6.3.26045"
  dgl: "1.1.3-patched"
  tensorflow: "2.13.1-dtk"
  gromacs: "2026.3-opencl"
  openmm: "8.2.0"
runtime_images:
  torch: "runtime-torch-dtk26.04-py3.10:r3"
  dgl: "runtime-dgl-dtk26.04-py3.10:r3"
  tf: "runtime-tf-dtk26.04-py3.10:r2"
  hpc: "runtime-hpc-dtk26.04:r1"
```

### 7.2 升级纪律（对应 `03` §6.1）

| 编号 | 规则 |
|---|---|
| VM-01 | 任何计算栈版本升级必须走独立 MR + 架构审批，并附「精度对齐 + 性能基准」回归报告 |
| VM-02 | 升级回归在 `dev` 用**同一 sample 输入**对比升级前后输出，关键指标偏差超阈值即阻断 |
| VM-03 | 禁止 pip 覆盖 `torch/dgl/tensorflow`（`07` §2.2），CI 检查 L1 Dockerfile 与 requirements |
| VM-04 | 版本矩阵变更必须同步更新 `03` §6.1、`07` §2.2 与本文 §7.1 三处，由 CI 检查一致性 |
| VM-05 | 业务侧 Python 依赖升级（安全补丁除外）每个大版本最多两次，集中处理 |

---

## 8. 流水线度量与健康度

| 指标 | 目标值 | 采集方式 | 处置 |
|---|---|---|---|
| MR 流水线成功率 | ≥ 90% | GitLab 统计 | 低于目标 → 下个迭代做一次「红灯根因复盘」 |
| 流水线 P50 / P90 时长 | ≤ 15 min / ≤ 30 min | 同上 | 超时 → 检查缓存命中与受影响服务探测 |
| 主干红灯时长 | ≤ 2 h | 告警 | 超 2h 触发全员通知，暂缓合并 |
| 特性分支存活时间 | ≤ 5 工作日 | 分支列表 | 超期需在站会说明 |
| 单 PR 变更行数 | P90 ≤ 400 | MR diff 统计 | 超限在 Review 中要求拆分 |
| 镜像构建缓存命中率 | L1 ≥ 90%、L2 依赖层 ≥ 90% | Kaniko 日志 | 偏低 → 检查层顺序与 apt/pip 写法 |
| 部署失败率（dev） | ≤ 5% | 部署脚本结果 | 超限 → 复盘探针与迁移兼容性 |
| 制品可追溯完整率 | 100% | 抽查镜像 label 含 git sha、lock 摘要、构建流水线 ID | 缺失即 P1 缺陷 |

**镜像必需 label**（便于现场排障与追溯）：

```
org.opencontainers.image.source      = <仓库地址>
org.opencontainers.image.revision    = <git sha>
org.opencontainers.image.version     = <平台版本>
io.drp.pipeline.id                   = <流水线 ID>
io.drp.lock.sha256                   = <uv.lock 摘要>
io.drp.versions.sha256               = <versions.yaml 摘要>
io.drp.model.manifest.sha256         = <模型 manifest 摘要，仅 L2>
io.drp.build.time                    = <ISO8601>
```

---

## 9. 角色与权限

| 角色 | 权限 | 限制 |
|---|---|---|
| 开发 | 推送特性分支、发起 MR、触发 dev 部署 | 不可推 `main`、不可建 release tag |
| 评审人（Reviewer） | 审批 MR | — |
| 平台组（DevOps） | 维护 Runner、Harbor、devpi、流水线模板 | 变更流水线需 MR |
| 架构负责人 | 审批 L0/L1 变更、`versions.yaml` 变更、ADR | — |
| 发布经理 | 创建 release 分支与 tag、组装离线包 | tag 需双人复核 |
| 甲方运维 | prod 部署执行、介质校验 | 无代码权限 |

**受保护分支**：`main`、`release/*` → 禁止直推、要求 MR + ≥1 approve + CI 全绿 + 禁止强推。

---

## 10. 落地检查清单

- [ ] GitLab CE + Runner（app/dcu/perf 三类）已在内网可用，Runner 标签已配置
- [ ] Harbor 四个项目（`app`/`base`/`runtime`/`calc`）已创建，开启不可变 tag 与漏洞扫描
- [ ] devpi/Nexus 已预热本项目全部依赖（`uv sync` 可离线成功）
- [ ] `tools/` 下门禁脚本齐备：`lint_all.sh`、`affected.py`、`scan_outbound.py`、`forbidden_imports.py`、`license_check.py`、`model_gate.py`
- [ ] `.gitlab-ci.yml` 已包含 S0~S7 与 P-M1~P-M4，且受影响服务探测生效（全量跑一次 ≤ 30 min）
- [ ] `versions.yaml` 已建立并与 `03` §6.1、`07` §2.2 一致（CI 有校验）
- [ ] 模型包门禁 P-M1 可在无 DCU 环境跑通（用 FakeBackend + sample 数据）
- [ ] `release` 流程已演练一次：出包 → 空环境 install → upgrade → rollback 全成功
- [ ] 镜像必需 label 已全部注入，抽查 3 个镜像可反查到 commit 与流水线
- [ ] 告警：主干红灯、流水线失败、镜像扫描高危已接入值班通知

---

## 附录 A：`.gitlab-ci.yml` 骨架（示意，非最终实现）

```yaml
stages: [precheck, lint, unit, integration, build, scan, push, deploy]

variables:
  UV_CACHE_DIR: "$CI_PROJECT_DIR/.cache/uv"
  PIP_INDEX_URL: "https://devpi.internal/root/pypi/+simple/"   # 内网
  NPM_CONFIG_REGISTRY: "https://nexus.internal/repository/npm/"

workflow:
  rules:
    - if: '$CI_PIPELINE_SOURCE == "merge_request_event"'
    - if: '$CI_COMMIT_BRANCH =~ /^(main|release\/.*)$/'

.changed:
  script:
    - uv run python tools/affected.py > affected.txt   # 输出受影响 service 列表

lint:
  stage: lint
  tags: [runner-app]
  script:
    - uv sync --all-packages --frozen
    - make lint
    - uv run python tools/scan_forbidden.py
    - uv run python tools/scan_outbound.py

unit:
  stage: unit
  tags: [runner-app]
  script:
    - uv run pytest -m "not integration" --cov --cov-report=xml --junitxml=report.xml
  artifacts:
    reports: { junit: report.xml, coverage_report: { coverage_format: cobertura, path: coverage.xml } }

integration:
  stage: integration
  tags: [runner-app]
  services: []          # 由 compose 起 PG/Redis/MinIO
  script:
    - docker compose -f deploy/dev/docker-compose.yaml up -d
    - make test-integration
    - make migrate-verify

build-image:
  stage: build
  tags: [runner-app]
  script:
    - /kaniko/executor --context . --dockerfile services/task/Dockerfile
        --destination harbor.internal/drp/app/drp-task:$CI_COMMIT_SHORT_SHA
        --cache=true --cache-repo harbor.internal/drp/app/cache

scan-image:
  stage: scan
  tags: [runner-app]
  script:
    - trivy image --exit-code 1 --severity HIGH,CRITICAL harbor.internal/drp/app/drp-task:$CI_COMMIT_SHORT_SHA

build-runtime:
  stage: build
  tags: [runner-dcu]        # ★ 必须带 DCU，07 §4.2 的 verify_runtime 才能通过
  rules:
    - if: '$RUN_RUNTIME_BUILD == "true"'   # 手动触发 + 架构审批
  script:
    - /kaniko/executor --dockerfile compute/runtime/dgl/Dockerfile ...

model-gate:
  stage: lint
  tags: [runner-app]
  rules:
    - changes: [compute/models/**/*]
  script:
    - uv run python tools/model_gate.py compute/models/$MODEL   # P-M1

model-smoke:
  stage: integration
  tags: [runner-dcu]        # P-M3
  rules:
    - changes: [compute/models/**/*]
  script:
    - make package MODEL=$MODEL && make smoke MODEL=$MODEL
```

## 附录 B：DCU Runner 配置要点

| 项 | 要求 |
|---|---|
| 设备挂载 | `/dev/kfd`、`/dev/dri` 挂入 Runner 容器；`LD_LIBRARY_PATH` 含 `/opt/hyhal/lib:/opt/dtk-26.04/lib` |
| 并发限制 | 每台 DCU Runner 并发 1（避免构建任务互相干扰显存） |
| 标签 | `runner-dcu`（构建）、`runner-perf`（压力，按需借用弹性卡） |
| 隔离 | 用 `--device` 显式限定单卡（如 `--device /dev/dri/renderD128`），禁止整机独占 |
| 健康检查 | Runner 启动时执行 `hy-smi` 与 `verify_runtime`，失败则 Runner 置为不可用并告警 |
| 与业务隔离 | DCU Runner 所在节点在 `dev` 集群内，但与业务 Pod 用 taint/toleration 隔离（`03` §4.3） |
