# SciMiner 模型镜像模板

该目录是管理员添加新模型时使用的标准模板。构建上下文包含 Dockerfile、忽略规则和模型源码：

```text
├── .dockerignore
├── Dockerfile
├── README.md
├── model/
└── platform_adaptor/
```

镜像运行目录固定分为两层：

```text
/opt/sciminer/
├── model/
│   ├── MODEL_PACKAGE.yaml
│   ├── README.md
│   ├── platform_run.sh
│   ├── requirements.txt
│   └── 模型代码、权重、配置
└── platform_adaptor/
    ├── entrypoint.sh
    ├── platform_run_v2.sh
    ├── object_storage.py
    └── requirements.txt
```

Pocket2Mol 这类带大型环境归档的构建上下文使用多阶段 Dockerfile：归档只在构建阶段解包，最终运行镜像不包含 `environment.tar.zst`、`legacy-source.tar.zst` 或旧版本导出归档。

## 目录职责

### `model/`

只放模型自身内容：

- 模型代码和推理入口；
- 模型权重或权重校验清单；
- 模型依赖；
- 模型侧 `platform_run.sh`；
- `MODEL_PACKAGE.yaml` 和模型说明。

模型侧入口必须接收平台统一参数：

```text
--model-root
--task-id
--input-dir
--output-dir
--params-json
--work-dir
--device
```

### `platform_adaptor/`

只放平台适配逻辑，不放模型算法：

- 接收 K8s Job 传入的统一参数；
- 从 MinIO 下载输入对象并校验 SHA-256；
- 调用 `model/platform_run.sh`；
- 校验模型输出后先上传产物文件，再上传 `result.json`；
- 保持输入、输出和退出码契约稳定。

普通用户不修改该目录。管理员审核模型时，重点检查该层是否把模型私有路径、主机路径和凭据泄漏到平台契约中。

## 当前 Pocket2Mol bundle 转换

浮浮酱提供了转换脚本，可以把现有 bundle 转成标准构建上下文：

```bash
python scripts/create_model_image_context.py \
  --bundle-dir /data/zhouyc/cpumodel_sciminer/model/kaiwu-venv-model-bundles/kaiwu-venv-model-bundles-20260805T074701Z/pocket2mol-pocket-ligand-generation \
  --output-dir /data/zhouyc/cpumodel_sciminer/model-build/pocket2mol-pocket-ligand-generation-v4
```

脚本会生成：

```text
pocket2mol-pocket-ligand-generation-v4/
├── .dockerignore
├── Dockerfile
├── README.md
├── model/
│   ├── legacy-source.tar.zst
│   ├── environment.tar.zst
│   ├── MODEL_PACKAGE.yaml
│   ├── README.md
│   ├── platform_run.sh
│   └── src/
└── platform_adaptor/
    ├── entrypoint.sh
    ├── platform_run_v2.sh
    ├── object_storage.py
    └── requirements.txt
```

`legacy-source.tar.zst` 和 `environment.tar.zst` 只作为构建输入，Dockerfile 会在镜像构建阶段解包；它们不属于平台运行时的可编辑配置。

## 构建和导出

Pocket2Mol 当前 bundle 是 `linux/amd64`、CUDA 模型，构建机器执行：

```bash
docker buildx build \
  --platform linux/amd64 \
  -t sciminer/pocket2mol-pocket-ligand-generation:0.1.4 \
  --load \
  /data/zhouyc/cpumodel_sciminer/model-build/pocket2mol-pocket-ligand-generation-v4

docker save sciminer/pocket2mol-pocket-ligand-generation:0.1.4 \
  | gzip -c > pocket2mol-pocket-ligand-generation-0.1.4-linux-amd64.tar.gz

sha256sum pocket2mol-pocket-ligand-generation-0.1.4-linux-amd64.tar.gz
```

然后由管理员通过平台的镜像导入 API 上传，不要把 `latest` 注册为模型版本。

## 管理员审核清单

- `model/platform_run.sh` 不依赖宿主机路径；
- 模型权重在镜像内或有不可变校验清单；
- `platform_adaptor/entrypoint.sh` 为唯一容器入口；
- MinIO SDK 依赖固定在 `platform_adaptor/requirements.txt`；
- 输入从平台下发的对象描述符下载到 `input-dir`，并校验 SHA-256；
- 输出写入 `output-dir`，且 `result.json` 最后上传；
- 成功时生成平台约定的 `result.json`；
- 资源需求映射到平台 Resource Profile；
- 镜像使用 manifest digest 注册；
- 未经过实际 K8s Job smoke test 前，不标记为 `published`。
