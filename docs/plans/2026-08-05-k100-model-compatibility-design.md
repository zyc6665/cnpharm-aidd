# K100 Model Compatibility And Binary Delivery Design

## 背景

本轮国产化测试目标是在三周内确认 K100 + `2.7.1-ubuntu22.04-dtk26.04-py3.11` 能否跑通现有模型推理，并把验证过程沉淀成可复用的平台交付规范。商业测试机不应暴露完整模型源码，因此第一批必须至少完成 MolP-PC 的 `.so + 薄入口 + 权重` 二进制交付模板。

## 核心原则

平台侧 Interface 固定：平台只认识标准输入目录、标准输出目录、`platform_run.sh`、manifest、Artifact 和任务日志。不同模型、不同硬件、不同调度系统的差异都放到模型侧 Adapter 或执行 Adapter 中消化。

模型侧 Interface 固定：每个模型包对外只暴露一个运行入口，接收平台标准参数，输出 `result.json` 和标准 Artifact。模型内部可以保留原始推理实现、二进制扩展、权重加载和硬件适配逻辑，但这些实现细节不泄漏给平台。

商业测试机只放可运行交付物：不上传核心 `.py` 源码，不上传 Cython 生成的 `.c` 文件，不上传构建脚本中的敏感路径。兼容性探针可以上传最小 shell/Python 检测脚本；正式推理测试上传二进制包、权重、manifest 和样例输入。

## 三周节奏

### 第一周：模型兼容性测试

目标是确认 K100 + DTK 容器能否跑通模型推理。顺序为 MolP-PC、MSIGN、Pocket2Mol/GCDM、LVpocket/MMCD/TheraPainter。每个模型输出一份兼容性报告，记录 Python 版本、依赖安装方式、DTK/K100 算子问题、输入输出是否符合平台标准。

MolP-PC 是第一批模板模型。先用旧 cp38 包做内部 ABI 探针，快速判断旧环境能否在目标容器中启动；随后基于目标镜像 py3.11 构建 `.so + 薄入口 + 权重` 二进制交付包，作为后续模型迁移模板。

### 第二周：平台兼容性测试

目标是验证平台任务执行链路可以从当前 SSH + `docker exec` 过渡到 K100 容器执行模式。平台不引入模型专用分支，只新增或完善执行 Adapter。任务中心必须能展示任务状态、远端日志、进度消息和标准 Artifact。

### 第三周：架构收口

目标是把一次性迁移脚本收敛为 Tool Package v2 规范。完善模型侧 Adapter 模板、二进制包 manifest 校验、输入输出 Artifact 校验、执行层 Interface 和部署文档。后续 Slurm/K8s 只替换执行 Adapter，不改变模型包 Interface。

## 交付物

- `MolP-PC` K100 兼容性报告。
- `MolP-PC` 二进制交付包模板。
- 所有模型的兼容性矩阵。
- K100 容器执行 Adapter 验证记录。
- Tool Package v2 二进制交付规范。

## 风险

- 旧 cp38 环境可能依赖 CUDA/NVIDIA wheel，不能直接在 K100/DTK 上运行。
- py3.11 会要求重新构建 Cython 扩展和部分 Python native wheel。
- 国产加速卡算子兼容性可能成为主要阻塞点，不能只按 Python 包安装成功判断模型可用。
- `.so` 保护 Python 源码，但不保护权重；权重加密可以作为第二阶段增强。

