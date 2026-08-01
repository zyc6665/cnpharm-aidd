# Prompt for Codex or Claude Model-Side Platformization

你正在把一个新拿到的原始模型代码库整理成 SciMiner 模型侧规范包。请严格按以下规则执行。

## 目标

平台契约固定，模型代码适配平台。不要修改平台后端或前端，不要为单个模型新增平台字段。
你只能修改模型包目录内的源码、runtime wrapper、样例、测试和说明文档。

## 必须产出的文件

- `MODEL_PACKAGE.yaml`
- `MODEL_PACKAGE_GUIDE.md`
- `README.md`
- `.gitignore`
- `platform_run.sh`
- `src/<runtime_package>/`
- `tests/test_model_package_runtime_contract.py`
- `weights/WEIGHTS.md`
- `wheelhouse/README.md`

## 工作步骤

1. 阅读原始模型 README、入口脚本、参数、依赖、权重加载路径和输出文件。
2. 把原始代码放入 `original_model/` 或项目已约定的源码目录。
3. 把真实权重放入 `weights/`，但不要提交权重文件。
4. 在 `MODEL_PACKAGE.yaml` 中声明模型入口、标准输入输出契约和 Runtime Env。
5. Runtime Env 必须包含首选 container 镜像 digest、conda-pack/venv-pack fallback、执行器支持和缓存策略。
6. 在 runtime wrapper 中实现输入解析、原始模型调用和 `result.v2` 输出收敛。
7. 保持 `platform_run.sh` 为薄入口，只调用 `python -m <runtime_package>.cli`。
8. 写轻量测试，不依赖 GPU、torch、dgl 或真实权重即可验证包装逻辑。
9. 扫描并移除账号、主机、私有地址、宿主机绝对路径、密钥和大文件。

## 禁止事项

- 禁止修改平台后端或前端。
- 禁止在模型包中提交真实凭据、私有部署地址、账号或宿主机绝对路径。
- 禁止提交权重、wheelhouse、缓存、运行输出或大型训练数据。
- 禁止把运行设备作为必填业务参数；设备属于部署 variant 执行上下文。
- 禁止要求 Executor 在任务执行时安装依赖或激活某个宿主机私有环境。
- 禁止只写 README 不写可测试 runtime wrapper。

## 推荐收口

完成后运行：

```bash
pytest tests/test_model_package_runtime_contract.py -q
python -m py_compile src/<runtime_package>/*.py
git diff --check
```

如果测试只验证包装逻辑，请明确说明它不代表模型科学结果或硬件兼容已验证。
