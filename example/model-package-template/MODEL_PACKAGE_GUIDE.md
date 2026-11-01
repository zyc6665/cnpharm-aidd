# Model Package Guide

这个目录是模型侧规范包模板。它解决的是“拿到原始模型代码和权重后，如何把模型源码整理成
可交给平台 Tool Package 继续适配的规范包”。

## 核心原则

平台契约固定，模型侧包负责适配输入、输出和运行方式。不要修改平台后端或前端来适配单个模型。

## 目录约定

- `original_model/`：放原始模型代码。除必要兼容修复外，不在这里写平台逻辑。
- `weights/`：放本地权重。真实权重不提交 Git，只保留 `WEIGHTS.md`。
- `src/model_runtime_template/`：标准 runtime wrapper，负责输入解析、原始模型调用、结果收敛和 CLI。
- `platform_run.sh`：模型侧标准适配入口，不是原始模型旧脚本；只解析通用任务参数
  （包括 Tool Package runner 传入的 `--model-root`）并调用 runtime CLI。
- `examples/`：最小输入输出样例，供合同测试和人工 smoke test 使用。
- `tests/`：不依赖重模型环境的模型包结构与结果收敛测试。
- `MODEL_PACKAGE.yaml`：模型侧元数据和标准输入输出声明。

## Runtime Env / 执行器无关运行环境

模型包必须声明可复制的 Runtime Env，而不是依赖某台机器上已经存在的 conda 环境。
首选运行时是带镜像 digest 的 container；当 Slurm 或受限集群不能运行容器时，才使用 conda-pack
或 venv-pack 作为 fallback。

关键规则：

- `environment.yml` 和 `requirements.txt` 是构建线索，不是生产运行时产物。
- `MODEL_PACKAGE.yaml.runtime.artifacts.primary` 记录首选容器镜像和镜像 digest。
- `MODEL_PACKAGE.yaml.runtime.artifacts.fallback` 记录 conda-pack 或 venv-pack 的 URI 和 SHA-256。
- Executor 不安装依赖，只选择已验证的 Runtime Env、挂载权重和输入输出目录，然后调用模型侧
  `platform_run.sh` 标准入口。
- 平台部署机器只做控制面、缓存和跳板，不作为模型代码、Python 环境或权重的唯一来源。

更多规则见 `docs/guides/model-runtime-packaging.md`。

## 适配步骤

1. 把原始模型源码放入 `original_model/`，把权重放入 `weights/`。
2. 修改 `MODEL_PACKAGE.yaml` 的 `slug`、`name`、`version`、`legacy_entrypoint` 和标准契约。
3. 在 `MODEL_PACKAGE.yaml.runtime` 中声明 container、conda-pack fallback、执行器支持和缓存策略。
4. 在 `legacy_predict.py` 里调用原始模型入口，只在这里处理模型私有参数和文件布局。
5. 在 `result_builder.py` 里把原始输出收敛为 `aidd.sciminer/result`。
6. 保持 `platform_run.sh` 是薄入口，接受 `--model-root`、`--input-dir`、`--output-dir`、
   `--params-json`、`--work-dir`、`--device` 等通用参数，不写死账号、主机、容器名或宿主机路径。
7. 补充 `tests/test_model_package_runtime_contract.py`，至少覆盖输入校验、输出收敛和忽略规则。

## 与 Tool Package v2 的关系

模型侧规范包不替代 `example/model-platformization-template` 或实际 Tool Package v2。建议流程是：

1. 先把原始模型整理成这个模型侧规范包。
2. 再把模型侧规范包封装成 `tool-package`。
3. 平台只消费标准 Artifact 类型和 `result.v2`。

## 验证

从仓库根目录运行：

```bash
pytest example/model-package-template/tests/test_model_package_runtime_contract.py \
  test/test_model_package_template.py -q
```

如果没有完整依赖和权重，只运行合同测试，不声明模型科学结果已验证。
