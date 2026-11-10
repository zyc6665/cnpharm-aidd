# 中国医药 AI 药物研发平台 · DCU 适配复现与验证计划

| 项 | 内容 |
|---|---|
| 文档编号 | DRP-DCU-PLAN-v1.3 |
| 文档版本 | **v1.3**（2026-10-25 新增 §7 阶段 P4「先行验证环境 NVIDIA 8×4090 + k3s」，把 `D-08` 从「阻塞全部工作」降级为「阻塞模型标定与验收口径」；此前 v1.2 于 2026-10-23 生产级复审补齐，v1.1 于 2026-10-20 架构评审修订，变更明细见 `03A`） |
| 上游 | `03-系统架构设计说明书.md`、`07-模型交付与运行规范.md`、《模型海光兼容测试报告》（2026-08） |
| 状态 | **P4 可立即启动**（4090 环境）；**P0~P3 仍待 DCU 环境**（`D-08` 🔴） |

---

## 1. 现状与问题

### 1.1 已有成果

2026-08-19/20 在浪潮 CS5468H3（8×K100-AI）容器环境中完成验证，**报告结论为「兼容性通过」**：

| 组件 | 结论 | 性能证据 |
|---|---|---|
| Boltz-2 | ✅ | 8 卡并发 3 轮 24/24；238 aa wall p50 123s；吞吐 3.822 pred/min |
| LVpocket | ✅ | 工业级 soak 112/112；平均 wall 24~26s；显存峰值 4% |
| STD-Diff | ✅ | 64 分子/8 卡/1000 步 96.1s（≈3×） |
| Pocket2Mol | ✅ | fallback 路径 smoke + max_steps=5 复测 |
| MolP-PC | ✅ | 2 行输入 → 56 列输出 |
| MSIGN | ✅ | `predicted_affinity` = -11.0999 |
| PEARL | ✅ | CPU + DCU smoke |
| GROMACS | ✅ | 1AKI 完整 MD，生产 500000 步 |
| AutoDock Vina | ✅（CPU） | 1uw6，-6.535 kcal/mol |
| TheraPainter | ⚠️ | 环境与依赖通过，**完整 evolve smoke 产物待补** |
| AlphaFold（DCU） | ❌ | pLDDT/坐标 NaN |
| OpenFE/OpenMM（GPU） | ❌ | NVRTC/HIPRTC 失败 |

### 1.2 核心问题

> **机器已回收；适配是在「服务器上的目录」里做的，没有沉淀为镜像、权重包和 manifest。**

这意味着现有成果是 **一次性验证记录**，不是 **可交付资产**。重新拿到机器后，如果只是「照着报告再跑一遍」，会再次得到一堆无法复现到生产环境的目录。

### 1.3 复现目标（重新定义）

| 目标 | 产出物（必须可入库） |
|---|---|
| ① 基础环境资产化 | `base-dtk26.04` 基础镜像 + 4 个 L1 runtime 镜像 |
| ② 模型资产化 | 每个模型 → L2 镜像 + 权重包 + `manifest.yaml` + `sample/` |
| ③ 验证可重复 | `tests/verify_dcu.sh` 可一键复跑，产物可与 `sample/expected` 比对 |
| ④ 补齐缺口 | TheraPainter 完整 smoke；各模型显存/耗时基线采集 |
| ⑤ 性能基线入库 | 单卡/8卡并发/soak 的性能数据写入 manifest |

**判断标准**：复现结束时，`docker pull` 得到的镜像能在**任意**一台装好驱动的 K100-AI 节点上跑通，才算完成。

---

## 2. 环境申请清单（需立即向甲方/厂商提出）

### 2.1 硬件

| 项 | 要求 | 说明 |
|---|---|---|
| 服务器 | 浪潮 CS5468H3 或同配置，8×K100-AI | 建议至少 1 台用于复现；生产需 2 台 |
| 用途 | **复现阶段需独占**，避免与他人争抢 | 编译 DGL/GROMACS 耗时长 |

### 2.2 软件与介质

| 项 | 版本/内容 | 提供方 |
|---|---|---|
| DTK | **26.04** 安装包 + 运行库 | 海光 / 浪潮 |
| HYHAL 运行库 | 随 DTK | 同上 |
| DCU 驱动 | 与内核匹配 | 同上 |
| PyTorch（DTK 适配） | **2.7.1** wheel / 镜像 | 海光光合社区（sourcefind.cn） |
| TensorFlow（ROCm） | **2.13.1** | 同上 |
| DGL | 1.1.3 源码 + DTK CUDA shim | 我方自编译 |
| GROMACS | 2026.3 源码（OpenCL build） | 开源 |
| Meeko / OpenBabel / RDKit | 实测版本 | 开源 |
| micromamba / uv | 环境管理 | 开源 |
| 模型权重与代码包 | Boltz-2 / LVpocket / STD-Diff / Pocket2Mol / MolP-PC / MSIGN / PEARL / TheraPainter | ✅ **已有备份（已确认，2026-10-19）** |

### 2.3 平台侧

| 项 | 要求 |
|---|---|
| 镜像仓库 | Harbor（可推镜像） |
| 对象存储 | MinIO（存放权重包） |
| K8s 集群 | 业务侧可用即可（**不要求 DCU device plugin**，DCU 机器不进 K8s，见 `09` / `13` §3.2） |
| 内网 PyPI | 可访问，用于构建期拉依赖 |
| 构建机 | 可运行 Kaniko（建议直接复用 DCU 节点做构建 Pod） |

> ✅ **已确认（2026-10-19）：原模型代码包与权重均有备份**，包含 `/workspace/DCU_test_success/*.tar.gz`、`/workspace/PEARL/...`、`alphafold-v2.3.2.tar.gz` 等。
> 因此复现工作的性质为「**把已有备份资产化为镜像 + 权重包 + manifest**」，而非「重新适配」，工作量显著下降。**首要动作**：立即将备份做一份异地只读归档（第二份副本），避免单点丢失。

---

## 3. 分阶段计划

### 阶段 P0：基础环境资产化（目标 5 个工作日）

| # | 任务 | 产出 | 通过标准 |
|---|---|---|---|
| P0-1 | 基础镜像 `base-dtk26.04` | Harbor 镜像 | 容器内 `hy-smi` 可见 8 张 DCU |
| P0-2 | `runtime-torch-dtk26.04-py3.10` | Harbor 镜像 | `torch==2.7.1`、`torch.version.hip==6.3.26045`、`torch.cuda.is_available()==True` |
| P0-3 | `runtime-dgl-dtk26.04-py3.10` | Harbor 镜像 | DGL 1.1.3 patched 编译成功；`dgl.graph(...).to('cuda:0')` + GATConv 通过 |
| P0-4 | `runtime-tf-dtk26.04-py3.10` | Harbor 镜像 | TF 2.13.1 matmul 落在 `/device:GPU:0`，设备名 K100_AI |
| P0-5 | `runtime-hpc-dtk26.04` | Harbor 镜像 | `gmx --version` 显示 OpenCL，clinfo 识别 K100_AI；Vina CLI 可用 |
| P0-6 | `drp-runner` + `drp-weight-fetcher` | Harbor 镜像 | 能下载输入、上传产物、写 result.json |

**关键动作**：P0 完成后**立刻把 4 个 runtime 镜像推到 Harbor**，这是本项目第一个真正可复用的资产。

### 阶段 P1：逐模型复现与入库（目标 10 个工作日）

按优先级排序，**先把 ★ 专项依赖的模型做完**：

| 优先级 | 模型 | 对应 ★ | 依赖 runtime | 关键验证 |
|---|---|---|---|---|
| **P1-1** | **Boltz-2** | S-01 结构预测 / S-04 亲和力 | torch | GFP 238aa 单卡；8 卡并发 3 轮 24 次 |
| **P1-2** | **LVpocket** | S-02 口袋预测 | tf | smoke + 8 卡并发 + GPU0 soak |
| **P1-3** | **STD-Diff** | S-03 分子生成 | torch | 8 分子单卡；64 分子 8 卡 |
| **P1-4** | **Pocket2Mol** | S-03 | torch(dgl) | fallback smoke + max_steps=5 |
| **P1-5** | **MolP-PC** | S-04 ADMET | dgl | 2 行输入 → 56 列 |
| **P1-6** | **MSIGN** | S-04 亲和力 | dgl | predicted_affinity 输出 |
| **P1-7** | **TheraPainter** | S-03 多肽 | torch | **补跑完整 evolve smoke，留存 output 与日志** |
| P1-8 | PEARL | — | dgl | CPU + DCU smoke |
| P1-9 | GROMACS | S-05 相关 | hpc | 1AKI 完整 MD 链路 |
| P1-10 | AutoDock Vina | S-05 筛选 | hpc | 1uw6 docking |
| P1-11 | gmx_MMPBSA / 自由能 | S-05 相关 | hpc | 依赖 GROMACS 产物 |

每个模型的复现动作（标准化）：

```
1 整理交付包（按 07 §2.1 目录结构）
2 写 manifest.yaml
3 构建 L2 镜像（FROM 对应 L1）
4 跑 sample/input → 比对 sample/expected
5 采集基线：单样本耗时、冷启动耗时、显存峰值、功耗/温度（hy-smi）
6 8 卡并发 + soak 压测（★ 专项相关模型必做）
7 推镜像 + 传权重 + 注册中心登记
```

### 阶段 P2：平台联调（目标 5 个工作日）

| # | 任务 | 通过标准 |
|---|---|---|
| P2-1 | ~~K8s device plugin 资源名确认~~ → **改为卡位绑卡确认**（v1.1） | 在 DCU 机器上 `hy-smi` 能看到 8 卡；`ROCR_VISIBLE_DEVICES=0` 启动容器后 `torch.cuda.device_count()==1` |
| P2-2 | 容器内设备名确认 | 容器内 `torch.cuda.device_count()==1`，逻辑编号 `cuda:0`（DGL 侧 `hip:0`） |
| P2-3 | BATCH 模式端到端 | 提交 Boltz-2 任务 → 排队 → 执行 → 产物入库 → 追溯包可导出 |
| P2-4 | RESIDENT 模式端到端 | LVpocket 常驻 → 队列消费 → 低延迟返回 |
| P2-5 | 工作流串联 | 结构预测 → 口袋 → 生成 → 预测的 DAG 跑通 |
| P2-6 | 冷启动治理验证 | 节点缓存命中后二次任务冷启动下降 ≥ 50% |

### 阶段 P3：缺口补齐与评估（并行，10 个工作日）

| # | 任务 | 说明 |
|---|---|---|
| P3-1 | **Boltz-2 MSA 方案评估** | 实测用 empty MSA（confidence 0.433/complex_plddt 0.512 不作为质量基准）。评估是否引入本地 MSA（reduced_dbs 610GB）或限定适用范围 |
| P3-2 | **OpenBabel 许可证替代评估** | 实测链路大量依赖 OpenBabel（PDBQT 准备、Mol2 后处理，警告 4703 条）。评估 RDKit 替代可行性 |
| P3-3 | ADMET 指标族映射 | MolP-PC 56 列 → PRD 定义的 ADMET 指标族，缺口用自研模型补 |
| P3-4 | 结构准备流水线 | PDB→PDBQT（Meeko + RDKit）标准化为平台能力 |
| P3-5 | 构象 / 药效团 | RDKit ETKDG + 药效团特征，CPU 侧实现 |
| P3-6 | 各模型显存基线补齐 | 复现阶段用 `hy-smi` 采集并回填 manifest |

---

## 4. 复现验证矩阵（每个模型的通过标准）

| 验证项 | 通过标准 | 记录字段 |
|---|---|---|
| 环境自检 | `torch.cuda.is_available()` 且设备名含 `K100_AI` | `frameworks`、`device` |
| 单样本 smoke | 退出码 0，产物齐全，与 `sample/expected` 一致 | `smoke` |
| 数值正确性 | 与 CPU 基线或参考值偏差在阈值内（**不得出现 NaN**） | `validation` |
| 冷启动耗时 | 记录模型加载/编译耗时 | `resources.coldBootSeconds` |
| 单样本耗时 | p50 / p95 | `resources.steadyStateSecondsPerItem`（稳定态）与 `resources.coldBootSeconds`（冷启）**分别记录** |
| 显存峰值 | `hy-smi` 采样最大值 | `device.memoryGB` |
| 8 卡并发 | 8 卡同时各跑 1 个任务，全部成功，设备字段匹配 | `validation.testedDevices` |
| soak | 单卡连续 ≥16 次，无 OOM / 无设备错配 / 无 ERROR | `validation` |
| 性能漂移 | 首尾四分位变化 < 20%，无持续退化 | `validation.notes` |

> **AlphaFold 前车之鉴**：必须把「数值正确性」列为**独立验收项**。AlphaFold DCU 就是 EXIT 0 但输出 NaN，只看退出码会误判为通过。

---

## 5. 排期建议（与主计划对齐）

| 周次 | 阶段 | 里程碑 |
|---|---|---|
| W1 | 环境申请 + **确认代码/权重备份是否存在** | 环境到位 |
| W2–W3 | P0 基础环境资产化 | 4 个 runtime 镜像入库 |
| W4–W6 | P1-1 ~ P1-6（★ 专项依赖模型） | **V3.0 §5.1~§5.4 四个 ★ 专项具备可运行模型** |
| W7 | P1-7 ~ P1-11 | 全模型入库 |
| W8–W9 | P2 平台联调 | 端到端跑通 |
| W6–W12（并行） | P3 缺口补齐 | 评估报告 |

**与主计划的冲突提示**：原计划 W6 完成设计基线。若 DCU 环境 W2 才到位，P1 需 W4–W6，**设计评审中关于模型选型的部分应基于本计划的实际产出确认，而非假定全部可用**。

---

## 6. 风险与应对

| 编号 | 风险 | 概率 | 影响 | 应对 |
|---|---|---|---|---|
| DR-01 | ~~原模型代码包/权重已随机器销毁~~ | — | — | ✅ **已解除：备份已确认存在**。剩余动作：立即做第二份异地只读归档 |
| DR-02 | DGL 1.1.3 patched 编译失败（依赖 DTK CUDA shim 细节） | 中 | 高（MolP-PC/MSIGN/PEARL 受阻） | 提前向海光索取编译说明；备选：改用 PyG fallback（Pocket2Mol 已验证该路径可行） |
| DR-03 | Boltz-2 重新适配后性能退化 | 中 | 中 | 以实测 123s / 3.822 pred/min 为基线，偏差 >30% 需定位 |
| DR-04 | TheraPainter 完整 smoke 仍不通过 | 中 | ★ S-03 多肽部分 | 备选多肽生成方案（PEARL 侧能力 + 自研序列优化） |
| DR-05 | 环境只能短期使用 | 高 | 高 | **P0 优先做镜像资产化**，先把环境固化下来，后续即使机器回收也不影响 |
| DR-06 | 复现结果与报告不一致 | 中 | 中 | 以复现实测为准更新基线，不迷信报告 |

---

## 7. 阶段 P4：先行验证环境（NVIDIA 8×4090 + k3s，v1.3 新增）

> **背景**：`D-08`（DCU 环境重新申请）是当前唯一真正卡住开工的 🔴 项，且排期不由我们掌握。经决策（`D-33`，2026-10-25）：**不等待 DCU，先用一套 NVIDIA 8×4090（Linux + NVIDIA 驱动 + Docker + k3s）把平台骨架、算力侧 Agent、卡位调度与部分模型跑通**，DCU 到达后只做「适配层替换 + 逐模型标定」。本节的定位是**降低 D-08 的实际影响面**，不是替代 P0~P3。

### 7.1 为什么这条路成立

| 论点 | 说明 |
|---|---|
| **卡位模型与硬件无关** | 最终形态是「一张卡一个容器，容器内 `DRP_DEVICE=cuda:0`」，靠 `ROCR_VISIBLE_DEVICES`（DCU）/ `NVIDIA_VISIBLE_DEVICES` + `CUDA_VISIBLE_DEVICES`（NVIDIA）把容器钉到单张物理卡。**隔离机制在两边同构**，`slots.yaml` 的「卡号→卡位→模型」映射表可以原样迁移 |
| **Agent 协议与硬件无关** | `drp-node-agent` 的职责是「拉起容器、注入环境变量、计时、上报心跳、到点终止」，只通过 `slot.deviceIds` 与硬件耦合。`09` §4.5 的卡位状态机（FREE/BUSY/FAULT）与探活逻辑无需改动 |
| **平台侧完全不感知硬件** | 业务代码只经过 `ComputeBackend`；`HTTPBackend` 只关心 `baseUrl + slotId`，不知道对端是 K100-AI 还是 4090 |
| **真正的适配成本被压缩到两层** | ① **镜像基座**（`base-dtk26.04` → `base-cuda12x`，runtime 层随之分裂）；② **逐模型算子 fallback 与标定**（cuEquivariance / torch_cluster / TF 兼容性 / 单件耗时基线）。这两层本来就是 `08` 的 P0、P1 内容，只是换个基座重做一遍，且**只做一次、不做两遍** |

### 7.2 两条硬约束（避免「先用 4090 凑合」变成技术债）

1. **不做设备抽象层**。禁止在代码里写 `if vendor == 'dcu'` 这类分支，也**不要**引入 `DRP_ACCELERATOR` 之类的厂商枚举变量。厂商差异**只允许出现在两个地方**：`slots.yaml` 的每卡位 `env{}`（注入厂商可见性变量）与镜像 tag / 基座镜像。违反这条，迁移时会把分支全带进生产。
2. **镜像必须成对存在**。DCU 镜像（`*-dtk26.04-py3.10`）与 NVIDIA 镜像（`*-cu121-py3.10`）**同 manifest、同模型版本、同 `reproducibility` 等级**，只有基座与 `deviceValue` 不同。`model_registry` 一期只登记一套（按实际交付环境），验证环境镜像以 `-dev4090` 后缀并存，**不得覆盖生产 tag**（`11` §1.2 的「禁止原地覆写」同样适用）。

### 7.3 这个环境不能证明什么（必须写进结论，避免验收争议）

| 项目 | 4090 验证环境 | 结论能否外推 |
|---|---|---|
| 平台骨架、状态机、幂等、追溯包 | 可完整验证 | ✅ **能**，直接作为生产依据 |
| 卡位独占、Agent 生命周期、心跳/超时/杀死 | 可完整验证 | ✅ **能** |
| 单件耗时基线（`07` `steadyStateSecondsPerItem` / `coldBootSeconds`） | 只能得到 NVIDIA 基线 | ❌ **不能**，`03` §5.2.1 与 §5.6 的数字必须在 K100-AI 上重测 |
| 显存容量 | 4090 24GB vs K100-AI 64GB | ❌ 不能，**且方向相反**：4090 通过的显存占用不代表 DCU 一定通过，反之 DCU 通过的在 4090 上可能 OOM（MD、大分子生成尤甚） |
| 复现等级与容差（`D-03-12` 的签字对象） | 只能在 DCU 上定 | ❌ 不能，**`D-03-12` 仍需真实 DCU** |
| 驱动/DTK 兼容性、device plugin 缺失的真实影响 | 无从验证 | ❌ 不能 |

> **一句话**：4090 环境能验证「**平台做得对不对**」，不能验证「**模型在 DCU 上跑得好不好**」。`D-08` 因此**不能关闭**，只能从「阻塞全部工作」降级为「阻塞模型标定与验收口径」。

### 7.4 阶段 P4 计划（目标 10 个工作日，可与 P0/P1 的等待期并行）

| # | 任务 | 产出 | 通过标准 |
|---|---|---|---|
| P4-1 | 环境清点与基线固化 | **`08A-P4环境清点与验证记录.md`**（已产出 v1.0） | 记录 OS/内核、`nvidia-smi` 输出（8 卡型号/显存/驱动/CUDA）、`docker info`、`k3s` 版本与节点角色、磁盘与网络布局 |
| P4-2 | `slots.yaml` 双形态验证 | 两份 slots 文件 | 同一份 schema 能分别描述 8×K100-AI 与 8×4090；Agent 以 `--config` 加载，**不改代码** |
| P4-3 | 单卡容器原子隔离验证 | 冒烟脚本 | 运行 `rocm`/`nvidia` 两套等价脚本：容器内 `torch.cuda.device_count()==1`，`DRP_DEVICE==cuda:0`，**`get_device_properties(0).uuid` 与 `slots.yaml` 声明的宿主卡一致**，且**两块卡同时跑互不串（各占各的卡，`nvidia-smi`/`hy-smi` 显存独立）** |
| P4-4 | `drp-node-agent` 全生命周期 | Agent 冒烟报告 | 拉起 → 心跳/进度 → 正常退出回填 → `SIGTERM` 宽限 60s → `SIGKILL` 兜底 → 卡位 FAULT/恢复；6 条路径全部有日志与状态留痕 |
| P4-5 | `drp-runner` 契约验证 | 契约测试报告 | 按 `07` §3.6 的 10 个变量与六步职责跑通：越界写 `DRP_OUT_DIR` 外被判失败、`result.json` 在 `/work` 根、`artifacts[].sha256` 正确回填 |
| P4-6 | 平台骨架联调 | 端到端录像 | 提交任务 → 排队 → 选卡位 → 执行 → 产物入 MinIO → 追溯包可下载 → 复算入口可用（**用 mock 模型**，不依赖 GPU） |
| P4-7 | 部分模型先行（见 §7.5） | 各模型 smoke 报告 | 每个模型给出「在 4090 上能否跑通 + 显存峰值 + 单件耗时 + 与报告基线的差异」 |
| P4-8 | 迁移清单（P4 的核心交付） | `P4-MIGRATION-CHECKLIST.md` | 逐条列出「DCU 到达后必须在真实卡上重做/重测的项」，含负责人与顺序；**这份清单就是 `D-08` 解除后的第一天工作内容** |

> **P4-3 的判据在首次实测后加强（2026-10-25）**：原来只要求 `device_count()==1`。实测发现「容器 `Up` + `nvidia-smi` 能看到卡 + 退出码 0」**三者同时成立时 GPU 仍可能完全不可见**（`CUDA_VISIBLE_DEVICES` 填错宿主卡号 → `count==0` 且无报错，见 `08A` §4）。因此判据加上 **`uuid` 与 `slots.yaml` 声明一致**，并要求该断言进入 Agent 的就绪自检（`09` §5.6 迁移纪律第 5 条）。
>
> **P4-1 的实际交付物改名为 `08A`**：原计划的 `P4-ENV.md` 已直接产出为独立文档 `08A-P4环境清点与验证记录.md`（含 P4-1/P4-3 结果与缺陷记录），不再单独建文件。后续 P4-2/P4-4~P4-8 的记录追加进同一份 `08A`。

### 7.5 4090 上先跑哪些模型

| 模型 | 4090 可行性 | 先跑的理由 | 需注意 |
|---|---|---|---|
| **Boltz-2** | ✅ 高（官方 CUDA 实现，需关 cuEquivariance） | ★ S-01/S-04 主链路；文档基线最全（24/24、p50 123s、loop 9~10s），**差异一出现就能定位** | 必须 `useMsa:false`、`numRecycles:3`；权重 SHA-256 与基线比对 |
| **AutoDock Vina** | ✅ 高（CPU 工具） | 只验证「CPU 分片 + 大批量漏斗」路径，与卡无关 | 顺带验证 128 核 CPU 池估算（`03` §5.6）在本机的等效表现 |
| **RDKit（ETKDG / 指纹 / 结构准备）** | ✅ 高（CPU） | D1 比特级复现的最强用例，可当场验证「复现包是否真的逐字节可复现」 | macOS/Linux 版本差异会导致指纹不同，记录 `rdkit_version` |
| **MolP-PC** | ⚠️ 中（TF 2.13 + DGL） | 验证 DGL 路径在 CUDA 下的编译与推理 | TF/DGL 版本组合需与 DCU 侧 `2.13.1 / 1.1.3 patched` 对齐，否则结果不可比 |
| **STD-Diff** | ⚠️ 中（`torch_scatter`） | 验证扩散生成 + D4 不可复现标注流程 | 显存波动大，记录峰值；`D4` 标注必须在 UI 上可见 |
| **LVpocket** | ⚠️ 中（TF 2.13） | 口袋预测主链路 | 若 TF 版本被迫升级，**结论不可与 DCU 基线比较**，只记「能跑」 |
| MD（GROMACS） | ❌ 不建议先做 | 耗时最长、显存/多卡行为差异最大，**在 4090 上的结论基本不可用** | 留到 DCU |
| TheraPainter / PEARL | ❌ 暂缓 | 多肽链路本身有未决问题（DR-04、smoke 未补），先解决再谈环境 | — |

> **顺序理由**：先跑「文档基线最全、判定最容易」的 Boltz-2 + 两个 CPU 工具，能在 1~2 天内确认「环境与契约是对的」；把 DGL/TF 这类版本耦合最重的放后面，避免一开始就陷进依赖地狱。

### 7.6 与主计划的关系

- P4 **不替换** P0~P1，而是把 P0 的「基础镜像资产化」拆成两条并行线：`base-dtk26.04 → DCU runtime`（等环境）与 `base-cuda12x → NVIDIA runtime`（**立即开工**）。
- P2（平台联调）**提前到 P4 做**，此时用 4090 或 mock 都可，**平台骨架的工期因此不再被 `D-08` 挡住**。
- P3（缺口补齐）与 `D-03-12` 的签字**仍必须等真实 DCU**，不变。

---

## 8. 立即行动项（本周）

| # | 行动 | 责任方 | 期限 |
|---|---|---|---|
| A-1 | ~~确认原模型代码包与权重是否有备份~~ → ✅ 已有备份 | 我方 | 已完成 |
| A-1b | **对备份做第二份异地只读归档**（防单点丢失） | 我方 | 立即 |
| A-2 | 提交 DCU 环境使用申请（注明需独占 + 需可推 Harbor） | PM | 立即 |
| A-3 | 索取 DTK 26.04 / PyTorch 2.7.1 / TF 2.13.1 离线安装包 | 我方 + 海光 | W1 |
| A-4 | 确认 8 张卡的物理编号与 `hy-smi` 输出对应关系（供 `slots.yaml` 使用） | 运维 | W1 |
| A-5 | 建立 Harbor 项目与 MinIO 桶（`drp-models`、`drp-assets`、`drp-results`、`drp-bulk`） | 运维 | W1 |
| A-6 | 编写 `verify_runtime.py` 构建期自检脚本 | 架构 | W1 |
| A-7 | 将本计划纳入项目主计划，调整里程碑 | PM | W1 |

> **v1.3 补充（2026-10-25，配合 `D-33` 与 §7 阶段 P4）**：A-2/A-3/A-4 的目标硬件仍是 DCU，**期限不变**（`D-08` 只是不阻塞开工，不是不做）；同时**另起一条 NVIDIA 4090 的并行行动线**，本周即可开始：
>
> | # | 行动 | 责任方 | 期限 |
> |---|---|---|---|
> | B-1 | 清点 4090 环境（`nvidia-smi -L` 8 卡、驱动版本、Docker + nvidia-container-toolkit、k3s 版本），产出 `P4-ENV.md` | 运维 | 立即 |
> | B-2 | 按 `09` §5.6 写两份 `slots.yaml`（DCU 版留作模板、4090 版用于验证），验证 Agent `--config` 切换**零代码改动** | 架构 + 运维 | W1 |
> | B-3 | 建独立 Harbor 项目与镜像命名规则（`-dev4090` / `-cu121` 后缀） | 运维 | W1 |
> | B-4 | 构建 L1 NVIDIA 基座镜像（`base-cu12x-py3.10`）并跑通 `verify_runtime.py` | 架构 | W1~W2 |
> | B-5 | 按 §7.5 顺序跑 smoke：Boltz-2 → Vina → RDKit → MolP-PC | 算法 | W2~W3 |
> | B-6 | 产出 `P4-MIGRATION-CHECKLIST.md`（DCU 到达后第一天要重做的事项） | 架构 | W3 |
>
> **纪律**：B 线**不占用** A-1b/A-2 的任何资源，两条并行；B 线的一切结论都带 `环境=dev4090` 标签（`12` §8.4），**不得回填 `03` §5.2.1 或作为 `D-03-12` 签字依据**。
