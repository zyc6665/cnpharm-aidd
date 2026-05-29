# AI 生成统一 `platform_run.sh` 指南

**版本**: v2.0  
**最后更新**: 2026-05-27  
**适用对象**: 平台管理员、课题组内部模型接入维护人员、Codex / Claude Code 等 AI 编码助手

---

## 1. 文档目的

这份文档不是普通说明书，而是给 AI 用的**执行规范**。

目标只有一个：

- 让 AI 在阅读模型代码后，稳定地产出一份**可以直接接入本平台 `ssh_job` 执行链路**的 `platform_run.sh`

这里的“可以直接接入”有明确含义：

1. 平台能够上传输入文件和 `params.json`
2. 平台能够通过 SSH 调用脚本
3. 脚本能够运行模型真实入口
4. 脚本能够生成标准 `result.json`
5. 平台能够拉回 `logs/` 和 `artifacts/`

这份文档面向的是“**AI 应该怎么做**”，不是“管理员可以自由发挥怎么接”。

---

## 2. 使用场景

适用于以下情况：

- 模型已经在远程服务器或现有容器中跑通
- 不想再为每个模型单独封装 FastAPI 服务
- 平台只需要受控地完成：
  - 上传输入
  - 远端执行
  - 拉回结果

不适用于以下情况：

- 模型尚未跑通
- 没有明确入口脚本或入口函数
- 需要高并发在线 API 推理
- 需要流式日志、流式 token 返回、交互式会话

---

## 3. 平台执行模型

平台侧 `ssh_job` 的目标流程固定为：

```text
平台创建任务
  ->
平台准备本地任务目录
  ->
平台上传 input/ 与 params.json 到远端
  ->
平台通过 SSH / docker exec 调用 platform_run.sh
  ->
模型在远端写出 output/result.json、output/logs/run.log、output/artifacts/*
  ->
平台拉回 output 目录
  ->
平台入库结果文件并更新任务状态
```

因此，`platform_run.sh` 的定位必须非常明确：

- 它是**模型侧统一适配层**
- 它不是新的推理服务
- 它不是新的框架层
- 它只负责把平台标准输入映射到模型原始入口命令

AI 的职责是：

- 理解模型已有运行方式
- 选择第一版最适合接入的平台能力
- 生成统一 `platform_run.sh`
- 生成或补全 `MODEL_DELIVERY.md`

AI **不应该**：

- 重写模型核心算法
- 发明新的推理流程
- 把多个能力一次性都接进去
- 同时生成 FastAPI、Dockerfile、平台后端逻辑

---

## 4. 硬性契约

这一节是最重要的。AI 生成的脚本必须遵守这些契约。

### 4.1 文件位置

默认放在模型项目根目录：

```text
<MODEL_ROOT>/platform_run.sh
```

如果模型实际运行在容器内，则 `entrypoint` 应指向容器内路径，例如：

```text
/workspace/GCDM-2model_claude/platform_run.sh
```

### 4.2 调用参数

脚本必须支持以下参数：

```bash
bash "./platform_run.sh" \
  --task-id "task-001" \
  --input-dir "/tmp/platform-jobs/task-001/input" \
  --output-dir "/tmp/platform-jobs/task-001/output" \
  --params-json "/tmp/platform-jobs/task-001/params.json"
```

可选参数：

```bash
--work-dir "/tmp/platform-jobs/task-001/work"
--device "cuda:0"
```

要求：

1. 不得擅自改参数名
2. 不得要求平台额外传递未约定参数
3. 可选参数未提供时，脚本必须自己给出合理默认值

### 4.3 输入目录约定

平台会准备：

```text
<TASK_DIR>/
├── input/
├── output/
├── work/
└── params.json
```

含义：

- `input/`：用户上传文件
- `output/`：平台约定的最终输出目录
- `work/`：模型运行过程中的中间文件目录
- `params.json`：平台传给模型的结构化参数

AI 生成的脚本必须遵守：

1. **只读** `input/`
2. 中间文件写入 `work/`
3. 最终结果写入 `output/`
4. 不得把最终产物散落在其他目录

### 4.4 `params.json` 约定

平台生成的 `params.json` 标准结构如下：

```json
{
  "task_id": "24c62e2f-c673-4bbe-a87a-b341a72db0ab",
  "task_name": "pocket_generation",
  "params": {
    "n_samples": 1,
    "sanitize": false,
    "relax": false,
    "resamplings": 1,
    "jump_length": 1,
    "device": "cuda:0"
  },
  "input_files": {
    "pocket_pdb": "input/3rfm_a2a-pocket10.pdb"
  },
  "uploaded_files": [
    {
      "file_id": "f4ec655c-9495-4377-ba5f-72939ea9888d",
      "filename": "3rfm_a2a-pocket10.pdb",
      "path": "input/3rfm_a2a-pocket10.pdb"
    }
  ],
  "files": [
    "input/3rfm_a2a-pocket10.pdb"
  ]
}
```

AI 生成脚本时必须遵守：

1. `input_files` 中的路径先按**相对任务目录逻辑路径**理解
2. 脚本内部将其转换为绝对路径
3. `params` 是模型参数主入口
4. `task_name` 用于模型能力分派
5. 若 `uploaded_files` 与 `files` 存在，应视为辅助信息，不得作为唯一数据来源

### 4.5 输出目录约定

脚本成功或失败后，`output/` 中至少必须有：

```text
output/
├── result.json
├── logs/
│   └── run.log
└── artifacts/
```

要求：

1. `logs/run.log` 必须存在
2. `result.json` 必须存在
3. 需要平台回收的文件必须统一放进 `artifacts/`
4. 即使失败，也应尽量写出 `run.log` 和 `result.json`

### 4.6 `result.json` 约定

成功时推荐结构：

```json
{
  "success": true,
  "message": "GCDM pocket generation completed",
  "outputs": {
    "generated_molecule_count": 1
  },
  "artifacts": [
    {
      "name": "generated_molecules.sdf",
      "path": "artifacts/generated_molecules.sdf",
      "content_type": "chemical/x-mdl-sdfile"
    }
  ],
  "metrics": {
    "duration_sec": 346.0
  }
}
```

失败时推荐结构：

```json
{
  "success": false,
  "message": "GCDM execution failed",
  "error": {
    "code": "MODEL_EXECUTION_FAILED",
    "details": "stderr or short traceback"
  }
}
```

硬性要求：

1. 必须有 `success`
2. 必须有 `message`
3. 成功时建议包含 `outputs`
4. 成功时如有回传文件，必须在 `artifacts` 中列出
5. 失败时建议包含 `error.code` 和 `error.details`

### 4.7 退出码约定

- 成功：`exit 0`
- 失败：非 `0`

平台同时依赖：

1. shell 退出码
2. `result.json.success`

所以 AI 生成脚本时不得只写日志不返回退出码，也不得只返回退出码不写 `result.json`。

---

## 5. AI 生成脚本时的强约束

AI 必须遵守以下规则。

### 5.1 必须做的事

1. 优先复用项目现有入口脚本、CLI、推理函数
2. 第一版只选择一个能力接入平台
3. 明确记录所选能力边界
4. 用 `python` 标准库解析 `params.json`
5. 把模型关键输出复制到 `output/artifacts/`
6. 写完整 `output/logs/run.log`
7. 写标准 `output/result.json`
8. 显式处理工作目录、checkpoint、conda 环境或解释器路径
9. 如果模型要求 GPU，要明确使用哪个设备参数

### 5.2 禁止做的事

1. 不得重写核心模型逻辑
2. 不得凭空编造输入字段
3. 不得把所有模型能力一次性接进去
4. 不得依赖 `jq`、`yq` 等默认未安装工具
5. 不得把输出文件散落在 `work/` 之外又不复制到 `artifacts/`
6. 不得把平台契约改成 AI 自己发明的新协议
7. 不得生成与本次目标无关的 FastAPI、Dockerfile、后端代码

### 5.3 遇到不确定信息时

AI 应该：

1. 保守处理
2. 使用现有 README / example / config 推断
3. 在 `MODEL_DELIVERY.md` 中标注“待确认”
4. 在脚本注释中说明假设

AI 不应该：

1. 为了让脚本看起来完整而伪造字段
2. 随意拼接不存在的 checkpoint、配置或路径

---

## 6. AI 阅读模型代码时必须提取的信息

在开始生成 `platform_run.sh` 前，AI 至少要先确认这些信息：

1. 第一版最适合接的平台能力是什么
2. 真实入口文件是什么
3. 真实入口命令是什么
4. 输入文件是什么格式
5. 输出文件最终在哪里生成
6. 是否依赖 GPU
7. 是否依赖特定 conda 环境
8. 是否必须切换工作目录
9. 是否必须指定 checkpoint / config / weights
10. 是否存在官方 example / smoke test

如果项目支持多个任务，例如：

- docking
- pocket generation
- linking
- peptide generation

第一版必须只选一个，并在 `MODEL_DELIVERY.md` 中明确：

- 本次接入能力
- 暂不支持能力

---

## 7. AI 输出物清单

AI 的交付物至少应包含：

1. `<MODEL_ROOT>/platform_run.sh`
2. `<MODEL_ROOT>/MODEL_DELIVERY.md`（若不存在则生成，若存在则补齐）
3. 简短说明：
   - 选了哪个能力
   - 真实入口是什么
   - 如何将平台参数映射到原始模型命令
   - 哪些地方仍待确认

如果 AI 只生成了脚本，没有同步补文档，这次任务不算完成。

---

## 8. 推荐脚本结构

AI 生成的 `platform_run.sh` 推荐采用下面的结构，而不是自由发挥。

```bash
#!/usr/bin/env bash
set -euo pipefail

TASK_ID=""
INPUT_DIR=""
OUTPUT_DIR=""
PARAMS_JSON=""
WORK_DIR=""
DEVICE=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --task-id) TASK_ID="$2"; shift 2 ;;
    --input-dir) INPUT_DIR="$2"; shift 2 ;;
    --output-dir) OUTPUT_DIR="$2"; shift 2 ;;
    --params-json) PARAMS_JSON="$2"; shift 2 ;;
    --work-dir) WORK_DIR="$2"; shift 2 ;;
    --device) DEVICE="$2"; shift 2 ;;
    *) echo "Unknown argument: $1" >&2; exit 2 ;;
  esac
done

mkdir -p "${OUTPUT_DIR}/logs" "${OUTPUT_DIR}/artifacts"
if [[ -z "${WORK_DIR}" ]]; then
  WORK_DIR="$(dirname "${OUTPUT_DIR}")/work"
fi
mkdir -p "${WORK_DIR}"

LOG_FILE="${OUTPUT_DIR}/logs/run.log"
exec > >(tee -a "${LOG_FILE}") 2>&1

python - <<'PY'
print("这里由 AI 根据具体项目补充 JSON 解析、命令拼装和 result.json 生成逻辑")
PY
```

推荐原因：

1. 参数解析统一
2. 目录结构统一
3. 日志行为统一
4. 后续平台联调成本更低

AI 可以在此基础上加少量辅助函数，但不应把脚本写成难以维护的大型工程。

---

## 9. 推荐的 Python 解析方式

AI 生成脚本时，解析 `params.json` 应优先使用 Python 标准库。

推荐模式：

```bash
python - <<'PY' "${PARAMS_JSON}" "${WORK_DIR}/platform_run_config.json"
import json
import sys
from pathlib import Path

params_json = Path(sys.argv[1])
output_json = Path(sys.argv[2])

payload = json.loads(params_json.read_text(encoding="utf-8"))
task_id = payload.get("task_id")
task_name = payload.get("task_name")
params = payload.get("params", {})
input_files = payload.get("input_files", {})

resolved = {
    "task_id": task_id,
    "task_name": task_name,
    "pocket_pdb": input_files.get("pocket_pdb"),
    "n_samples": params.get("n_samples", 1),
}

output_json.write_text(json.dumps(resolved, ensure_ascii=False, indent=2), encoding="utf-8")
PY
```

这样做的好处是：

1. 不依赖外部 JSON 工具
2. 路径和参数结构更容易审计
3. 出错信息更清晰

---

## 10. 推荐的失败处理模式

AI 生成的脚本必须考虑失败路径。

推荐模式：

1. 一开始就创建 `output/logs`、`output/artifacts`
2. 用 `trap` 或显式错误分支兜底
3. 执行失败时尽量写出 `result.json`
4. `result.json` 中写短错误摘要
5. 完整错误上下文留在 `run.log`

推荐思路：

```bash
write_failure_result() {
  local message="$1"
  python - <<'PY' "${OUTPUT_DIR}/result.json" "${message}"
import json
import sys
from pathlib import Path

result_path = Path(sys.argv[1])
message = sys.argv[2]

payload = {
    "success": False,
    "message": message,
    "error": {
        "code": "MODEL_EXECUTION_FAILED",
        "details": message,
    },
}
result_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
PY
}
```

---

## 11. AI 标准工作流

建议 AI 严格按下面步骤执行。

### 第一步：阅读项目

优先阅读：

- `README.md`
- `MODEL_DELIVERY.md`（如果已有）
- `requirements.txt`
- `environment.yml` / `environment.yaml`
- `configs/`
- `scripts/`
- `examples/`
- `weights/`
- `checkpoints/`

### 第二步：选定单一能力

必须回答：

- 第一版接什么能力
- 为什么选这个能力
- 它的最小输入是什么
- 它的最小输出是什么

### 第三步：锁定原始入口

必须明确：

- 入口脚本路径
- 入口命令
- 必须的参数
- 必须的权重 / 配置 / 环境

### 第四步：生成 `platform_run.sh`

映射规则：

- 平台输入 -> 模型原始命令
- 模型输出 -> 平台标准输出目录

### 第五步：生成或补齐 `MODEL_DELIVERY.md`

必须写明：

- 能力边界
- 输入字段
- 输出字段
- 示例调用
- 待确认项

### 第六步：自检

AI 在回复里必须主动检查：

1. 是否仍在复用原始模型入口
2. 是否写出了 `result.json`
3. 是否写出了 `run.log`
4. 是否把产物复制到了 `artifacts/`

---

## 12. 给 AI 的标准提示词

下面这段是推荐的主提示词。管理员只需要替换路径即可。

### 12.1 一次性生成提示词

```text
请读取以下模型代码目录，并基于代码真实结构生成或修改统一的 platform_run.sh：

- 模型代码目录：<MODEL_CODE_DIR>
- 优先阅读：README.md、MODEL_DELIVERY.md、requirements.txt、environment.yml、environment.yaml、configs/、scripts/、examples/、weights/、checkpoints/

目标：
1. 在 <MODEL_CODE_DIR> 下生成或修改 platform_run.sh。
2. 如果目录中没有 MODEL_DELIVERY.md，请参考 /data/zhouyc/cpumodel_sciminer/docs/guides/MODEL_DELIVERY.template.md 自动补一份。
3. 第一版只选择一个最适合作为平台工具的能力，不要试图覆盖整个项目所有任务。
4. 不要重写模型核心算法，只包装现有入口脚本、已有 CLI 或现有推理函数。

必须严格遵守 /data/zhouyc/cpumodel_sciminer/docs/guides/AI生成统一platform_run.sh指南.md 中的契约，尤其是：
1. platform_run.sh 必须支持：
   - --task-id
   - --input-dir
   - --output-dir
   - --params-json
   - 可选：--work-dir
   - 可选：--device
2. 必须在 output 目录中产出：
   - output/result.json
   - output/logs/run.log
   - output/artifacts/
3. result.json 至少包含：
   - success
   - message
   - 成功时建议包含 outputs、artifacts、metrics
   - 失败时建议包含 error.code、error.details
4. 不要依赖 jq 等默认未安装工具，优先用 python 标准库处理 JSON。
5. 如果需要激活 conda 环境、切换工作目录、指定 checkpoint、指定配置文件，请在脚本中显式写出。
6. 如果某些输入字段或输出行为无法从代码中确认，不要编造，请在 MODEL_DELIVERY.md 和脚本注释中标出“待确认”。

输出要求：
1. 直接修改或生成：<MODEL_CODE_DIR>/platform_run.sh
2. 如果缺失，则生成：<MODEL_CODE_DIR>/MODEL_DELIVERY.md
3. 在回复中说明：
   - 选择了项目中的哪一条能力作为第一版
   - 真实入口脚本或入口函数是什么
   - platform_run.sh 如何把标准输入映射到项目原始命令
   - 还有哪些待确认项

请不要生成 FastAPI 服务，不要生成 Dockerfile，不要生成平台后端代码。这次只做统一 platform_run.sh 和必要的 MODEL_DELIVERY.md。
```

### 12.2 修复已有脚本提示词

如果模型目录里已经有 `platform_run.sh`，但不能直接接平台，可以用下面这段：

```text
请审查并修复 <MODEL_CODE_DIR>/platform_run.sh，使其完全符合 /data/zhouyc/cpumodel_sciminer/docs/guides/AI生成统一platform_run.sh指南.md 的硬性契约。

重点检查：
1. 参数解析是否支持 --task-id / --input-dir / --output-dir / --params-json / --work-dir / --device
2. 是否一定生成 output/result.json
3. 是否一定生成 output/logs/run.log
4. 是否将需要平台回收的文件复制到 output/artifacts/
5. 是否仍在复用模型原始入口，而不是重写算法逻辑
6. 失败时是否能写出标准错误 result.json

如果发现待确认项，请不要编造，请在 MODEL_DELIVERY.md 中追加“待确认”说明。
```

---

## 13. 管理员验收清单

AI 输出后，管理员至少检查这些：

1. `platform_run.sh` 是否真实调用了现有模型入口
2. 第一版能力边界是否明确
3. 是否显式处理了环境、工作目录和 checkpoint
4. `input_files` 路径映射是否正确
5. `output/artifacts/` 是否收敛了回传文件
6. `result.json` 是否结构稳定
7. 失败路径是否有兜底
8. 是否仍保留原始模型运行方式，而不是自创新逻辑

若要做最小联调，建议先跑一次：

1. 准备一个最小输入样例
2. 手动执行 `platform_run.sh`
3. 检查：
   - `output/result.json`
   - `output/logs/run.log`
   - `output/artifacts/*`

---

## 14. 已验证接入样例

本仓库已经有一条真实跑通的 `ssh_job` 接入样例，可作为 AI 输出质量参考：

- 工具配置：[platform_tool.ssh_job.json](/data/zhouyc/cpumodel_sciminer/example/platform_tool.ssh_job.json)
- 已验证能力：`GCDM pocket generation`
- 已验证链路：
  - 平台上传 `pocket_pdb`
  - SSH 进入宿主机
  - `docker exec kaiwu`
  - 调用容器内 `platform_run.sh`
  - 远端生成 `result.json`、`run.log`、`generated_molecules.sdf`
  - 平台回收结果并将任务标记为 `SUCCESS`

这条样例说明：

1. 这份协议不是纸面设计，已经在平台中跑通
2. AI 生成脚本时应尽量向这种“薄适配层”风格靠拢

---

## 15. 推荐配套文档

相关文档入口：

- [09-SSH作业执行器集成方案.md](/data/zhouyc/cpumodel_sciminer/docs/design/09-SSH作业执行器集成方案.md)
- [MODEL_DELIVERY.template.md](/data/zhouyc/cpumodel_sciminer/docs/guides/MODEL_DELIVERY.template.md)
- [模型交付与AI生成FastAPI服务指南.md](/data/zhouyc/cpumodel_sciminer/docs/guides/模型交付与AI生成FastAPI服务指南.md)
- [AI生成完整镜像服务与MODEL_DELIVERY指南.md](/data/zhouyc/cpumodel_sciminer/docs/guides/AI生成完整镜像服务与MODEL_DELIVERY指南.md)

如果目标是：

- **复用远端已有容器或环境**：优先看本文件
- **让 AI 生成统一 `platform_run.sh`**：优先看本文件
- **让 AI 生成完整 FastAPI / Docker 服务**：看 FastAPI / 完整镜像相关指南

---

## 16. AI 输出后的最小 Smoke Test 模板

这一节是给管理员直接执行的。

目标不是做完整回归，而是用一组最小输入快速确认：

1. `platform_run.sh` 能被调用
2. 参数能正确解析
3. 模型真实入口能跑起来
4. `output/result.json`、`output/logs/run.log`、`output/artifacts/` 会被正确产出

### 16.1 准备一个临时任务目录

建议先在模型所在机器或容器挂载宿主机上准备：

```bash
TASK_ROOT="/tmp/platform-smoke/task-001"
rm -rf "${TASK_ROOT}"
mkdir -p "${TASK_ROOT}/input" "${TASK_ROOT}/output" "${TASK_ROOT}/work"
```

如果不想用 `/tmp`，也可以改成你模型机器上的固定测试目录，例如：

```bash
TASK_ROOT="/data/zhouyc/platform-smoke/task-001"
```

### 16.2 准备最小输入文件

把一个最小样例输入文件复制到：

```bash
cp "<YOUR_SAMPLE_INPUT_FILE>" "${TASK_ROOT}/input/"
```

例如 pocket 生成任务：

```bash
cp "./examples/3rfm_a2a-pocket10.pdb" "${TASK_ROOT}/input/"
```

### 16.3 准备最小 `params.json`

管理员可以先手工准备一份最小参数文件：

```bash
cat > "${TASK_ROOT}/params.json" <<'EOF'
{
  "task_id": "task-001",
  "task_name": "pocket_generation",
  "params": {
    "n_samples": 1,
    "sanitize": false,
    "relax": false,
    "resamplings": 1,
    "jump_length": 1,
    "device": "cuda:0"
  },
  "input_files": {
    "pocket_pdb": "input/3rfm_a2a-pocket10.pdb"
  }
}
EOF
```

注意：

1. `input_files` 里写的是**相对任务目录逻辑路径**
2. 文件名必须和 `input/` 中真实文件名一致
3. 第一版 smoke test 应尽量把参数收小，例如：
   - `n_samples=1`
   - 最小 batch
   - 最少步数

### 16.4 在宿主机直接跑脚本

如果模型直接运行在宿主机环境中：

```bash
bash "./platform_run.sh" \
  --task-id "task-001" \
  --input-dir "${TASK_ROOT}/input" \
  --output-dir "${TASK_ROOT}/output" \
  --params-json "${TASK_ROOT}/params.json" \
  --work-dir "${TASK_ROOT}/work"
```

如果脚本支持 `--device`，也可以显式传：

```bash
bash "./platform_run.sh" \
  --task-id "task-001" \
  --input-dir "${TASK_ROOT}/input" \
  --output-dir "${TASK_ROOT}/output" \
  --params-json "${TASK_ROOT}/params.json" \
  --work-dir "${TASK_ROOT}/work" \
  --device "cuda:0"
```

### 16.5 在容器内跑脚本

如果模型运行在现有容器内，推荐直接用和平台一致的方式测试：

```bash
docker exec <CONTAINER_NAME> bash -lc '
bash "<CONTAINER_PLATFORM_RUN_SH>" \
  --task-id "task-001" \
  --input-dir "<CONTAINER_TASK_ROOT>/input" \
  --output-dir "<CONTAINER_TASK_ROOT>/output" \
  --params-json "<CONTAINER_TASK_ROOT>/params.json" \
  --work-dir "<CONTAINER_TASK_ROOT>/work"
'
```

例如类似本仓库已验证的方式：

```bash
docker exec kaiwu bash -lc '
bash "/workspace/GCDM-2model_claude/platform_run.sh" \
  --task-id "task-001" \
  --input-dir "/workspace/platform-jobs/task-001/input" \
  --output-dir "/workspace/platform-jobs/task-001/output" \
  --params-json "/workspace/platform-jobs/task-001/params.json" \
  --work-dir "/workspace/platform-jobs/task-001/work"
'
```

### 16.6 Smoke Test 完成后必须检查的文件

至少检查这三个位置：

```bash
ls -R "${TASK_ROOT}/output"
cat "${TASK_ROOT}/output/result.json"
tail -n 100 "${TASK_ROOT}/output/logs/run.log"
```

如果是容器内路径，则把命令换成容器内路径即可。

判断标准：

1. `output/result.json` 存在
2. `output/logs/run.log` 存在
3. `output/artifacts/` 中有期望输出文件
4. `result.json.success == true` 时，shell 退出码应为 `0`
5. `result.json.success == false` 时，`run.log` 中应能看到明确错误

### 16.7 推荐的结果核对清单

通过 smoke test 后，至少核对：

1. `result.json.message` 是否符合实际任务
2. `result.json.outputs` 是否包含关键统计
3. `result.json.artifacts` 中列出的路径是否真实存在
4. `run.log` 中是否记录了真实入口命令
5. `artifacts/` 中是否只有需要平台回收的文件

### 16.8 如果 smoke test 失败，优先排查什么

优先按这个顺序看：

1. `run.log` 是否已经写出
2. `params.json` 是否被正确解析
3. 输入文件路径是否和 `input_files` 一致
4. conda 环境 / Python 路径是否正确
5. checkpoint / config / weights 路径是否正确
6. 宿主机路径和容器内路径是否映射一致
7. 脚本是否只把中间文件写到了 `work/`，而没有把最终结果复制到 `artifacts/`

### 16.9 Smoke Test 通过后的平台接入前条件

只有以下条件全部满足，才建议导入平台：

1. 手工执行 `platform_run.sh` 成功
2. `output/result.json` 结构稳定
3. `output/artifacts/` 中产物完整
4. `run.log` 能够提供足够排障信息
5. `MODEL_DELIVERY.md` 已写清第一版能力边界
