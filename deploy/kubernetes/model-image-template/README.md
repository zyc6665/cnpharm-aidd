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

带大型环境归档的模型应使用多阶段 Dockerfile：归档只在构建阶段解包，最终运行镜像不包含构建归档或旧版本导出文件。

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

## 管理员构建流程

管理员在仓库外创建独立构建上下文，复制本目录模板后填入经审核的模型包：

```bash
cp -a deploy/kubernetes/model-image-template /secure-build/<tool-slug>
```

构建上下文中的 `model/` 放置模型代码、权重、依赖、说明和模型侧 `platform_run.sh`；`platform_adaptor/` 使用通用平台适配层。不得将模型源码、权重、环境归档或构建上下文提交到平台仓库。

使用匹配模型依赖和目标硬件的可信基础镜像构建。发布到 Registry 时使用管理员批准的仓库与版本：

```bash
docker buildx build \
  --platform <os/architecture> \
  -t <registry>/<namespace>/<tool-slug>:<version> \
  --load \
  /secure-build/<tool-slug>

docker save <registry>/<namespace>/<tool-slug>:<version> \
  | gzip -c > <tool-slug>-<version>.tar.gz

sha256sum <tool-slug>-<version>.tar.gz
```

管理员可将归档通过平台镜像导入功能上传至内部 Registry；也可按组织流程直接推送。注册工具时记录 Registry 返回的 manifest digest，不使用可变 tag 作为运行镜像身份。

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
