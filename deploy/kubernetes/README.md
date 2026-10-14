# Kubernetes 开发环境一体化部署

本套清单面向当前单节点 K3s 开发环境，一次部署 PostgreSQL、Redis、MinIO、私有 OCI Registry、持久卷、K8s Job RBAC，以及供当前本机后端连接的开发 NodePort。**平台 API 仍运行在当前开发机**；后端镜像尚未构建，因此集群 Celery Worker 保持为单独启用项，不会因默认部署产生拉取失败的 Pod。

这是开发/联调配置，不是生产高可用方案：数据库、Redis、MinIO 和 Registry 都是单副本；Registry 使用无认证 HTTP；NodePort 仅用于受控开发网络。生产环境应另行使用 TLS、认证、备份、网络策略和高可用存储。

## 一次部署

部署前确认 K3s 可用并有 `local-path` StorageClass：

```bash
kubectl get nodes -o wide
kubectl get storageclass local-path
```

先创建命名空间，再用安全生成的随机值创建 Secret。Secret 值不要写入 YAML、Git 或 shell 历史；下面用环境变量承接生成值：

```bash
kubectl apply -f deploy/kubernetes/namespace.yaml

export POSTGRES_PASSWORD="$(openssl rand -hex 24)"
export REDIS_PASSWORD="$(openssl rand -hex 24)"
export MINIO_ROOT_USER="sciminer-admin"
export MINIO_ROOT_PASSWORD="$(openssl rand -hex 24)"

kubectl -n sciminer-system create secret generic sciminer-postgres-credentials \
  --from-literal=POSTGRES_DB=scitool \
  --from-literal=POSTGRES_USER=scitool \
  --from-literal=POSTGRES_PASSWORD="$POSTGRES_PASSWORD" \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl -n sciminer-system create secret generic sciminer-redis-credentials \
  --from-literal=REDIS_PASSWORD="$REDIS_PASSWORD" \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl -n sciminer-storage create secret generic sciminer-minio-credentials \
  --from-literal=MINIO_ROOT_USER="$MINIO_ROOT_USER" \
  --from-literal=MINIO_ROOT_PASSWORD="$MINIO_ROOT_PASSWORD" \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl apply -k deploy/kubernetes
```

`kubectl apply -k deploy/kubernetes` 会部署 `sciminer-system`、`sciminer-model-jobs`、`sciminer-storage` 三个命名空间内的基础设施和最小权限 RBAC。等待服务就绪：

```bash
kubectl -n sciminer-system rollout status deployment/sciminer-postgres
kubectl -n sciminer-system rollout status deployment/sciminer-redis
kubectl -n sciminer-storage rollout status deployment/sciminer-minio
kubectl -n sciminer-storage rollout status deployment/sciminer-registry
kubectl get pvc -A
```

MinIO 第一次启动后，在 `http://<K3S节点IP>:30901` 登录控制台并创建 bucket `scitool-files`。不要把 MinIO root 凭据用于平台运行任务；创建单独的 client 用户，并只授予该 bucket 所需权限。

## 本机后端连接配置

本机后端应使用 K3s 节点可达 IP，不能使用 `localhost` 或集群内部 DNS。下列端口由开发 NodePort 暴露：

| 组件 | 地址 | 用途 |
| --- | --- | --- |
| PostgreSQL | `<K3S节点IP>:30432` | 本机 API 与 Worker 数据库 |
| Redis | `<K3S节点IP>:30379` | Celery Broker、结果后端和缓存 |
| MinIO API | `<K3S节点IP>:30900` | 本机 API 对象存储 |
| MinIO Console | `<K3S节点IP>:30901` | 管理 bucket 和开发凭据 |
| Registry | `<K3S节点IP>:30500` | 从构建机推送开发镜像 |

在本机 `backend/.env` 中设置（密码使用前面生成的值，MinIO 使用专用 client 凭据）：

```dotenv
DATABASE_URL=postgresql+asyncpg://scitool:<POSTGRES_PASSWORD>@<K3S节点IP>:30432/scitool
REDIS_HOST=<K3S节点IP>
REDIS_PORT=30379
REDIS_PASSWORD=<REDIS_PASSWORD>
CELERY_BROKER_URL=redis://:<REDIS_PASSWORD>@<K3S节点IP>:30379/1
CELERY_RESULT_BACKEND=redis://:<REDIS_PASSWORD>@<K3S节点IP>:30379/2
STORAGE_BACKEND=minio
MINIO_ENDPOINT=<K3S节点IP>:30900
MINIO_ACCESS_KEY=<MINIO_CLIENT_ACCESS_KEY>
MINIO_SECRET_KEY=<MINIO_CLIENT_SECRET_KEY>
MINIO_BUCKET=scitool-files
MINIO_SECURE=false
IMAGE_REGISTRY_ENDPOINT=http://<K3S节点IP>:30500
IMAGE_REGISTRY_IMAGE_PREFIX=<K3S节点IP>:30500/sciminer
```

`DATABASE_URL` 中的用户名/密码若含 URL 特殊字符需要 percent-encode。确保防火墙只允许可信开发机访问上述 NodePort，尤其不要将未认证的 Redis、PostgreSQL 或 HTTP Registry 暴露到公网。

## Registry 节点配置

开发 Registry 使用 HTTP，构建机推送可通过 `http://<K3S节点IP>:30500`。每台需要拉取该镜像的 K3s 节点都要在 `/etc/rancher/k3s/registries.yaml` 配置 HTTP mirror，然后重启 K3s：

```yaml
mirrors:
  "<K3S节点IP>:30500":
    endpoint:
      - "http://<K3S节点IP>:30500"
```

重启前确认维护窗口；这会重启节点上的 K3s 服务。生产环境必须改为 HTTPS、认证和受信任证书。

## 集群执行 Worker

`execution-worker.example.yaml` 是可选的 K8s/Celery Worker，不包含在默认 Kustomize 清单中。它要求先构建并推送后端生产镜像、创建 `sciminer-execution-worker-secrets` 和 `sciminer-model-jobs/sciminer-minio-client` Secret，再把 Worker 清单中的镜像 digest 替换为真实值。当前后端镜像还未构建，因此本次基础设施部署不会启动 Worker；这不会影响本机后端继续使用 K8s 中的 PostgreSQL、Redis、MinIO 和 Registry。

启用真实 K8s executor 前，必须在 `sciminer-model-jobs` 创建 MinIO client Secret（键名 `access-key`、`secret-key`），并确保 Worker Secret 中的数据库、Redis、MinIO、Celery 和 SSH 配置与当前环境一致。Worker 的 RBAC 只允许在模型 Job namespace 管理 Job、Pod、日志和事件，不允许读取 Kubernetes Secret。

管理员界面中的候选版本 Smoke 会创建真实平台任务，不会自动检查或修复基础设施。使用 Celery 执行模式时，必须先部署并确认 `sciminer-execution-worker` 可用；使用 direct 模式时，运行 API 的进程必须具备提交和观察 K8s Job 所需的集群连接配置。Smoke 前还要确认 `sciminer-model-jobs` 中的 MinIO client Secret、目标 bucket 权限以及目标节点的 Registry 拉取配置均已就绪。Tool Package 中的镜像 digest 只能证明镜像身份固定，不能证明镜像可拉取或模型推理正确。

可先检查基础组件和命名空间资源是否存在，不要输出 Secret 内容：

```bash
kubectl -n sciminer-system get deploy sciminer-postgres sciminer-redis
kubectl -n sciminer-storage get deploy sciminer-minio sciminer-registry
kubectl -n sciminer-model-jobs get secret sciminer-minio-client
kubectl get nodes -o wide
```

smoke image 遵循平台的 `aidd.sciminer/result.v2` 契约，运行后在 `/workspace/output/result.json` 生成带 SHA-256 的 `run_report@1` 输出；配置对象存储凭据和输入描述符后，它还会验证 MinIO 输入 staging、输出上传和 `result.json` 最后提交，不替代真实模型镜像的推理验证。

仓库只保留管理员使用的通用模型镜像构建模板：`deploy/kubernetes/model-image-template/`。具体模型的源码、权重、环境归档和镜像构建工作区（包括根目录下的 `model-build/`）均属于本地或制品存储，不应加入 Git 或随平台源码推送。

当前集群无法通过默认 Docker Hub 镜像代理拉取 MinIO，因此开发 Deployment 使用可访问的镜像代理，并固定到 manifest digest：

```text
docker.1panel.live/minio/minio@sha256:c7175077d39a8cc10c9fd611cdcc68b6a5b365793e9ac6f4198ffff1ef0fe555
```

该地址是基础设施依赖，正式环境应替换为组织批准的私有仓库镜像，并重新执行镜像来源与 digest 审核。

这些文件不会自动修改集群。镜像、凭据和对象存储准备完成后，由管理员审阅并手动执行部署命令。

`sciminer-execution-worker` 只在 `sciminer-model-jobs` namespace 拥有 Job、Pod、日志和事件的必要权限；`model-runner` 不允许读取 Kubernetes API。Registry 使用 HTTP 的 K3s 节点配置见上文“Registry 节点配置”。

## 3. Job 对象存储结果契约

启用真实 K8s executor 前，需要在 `sciminer-model-jobs` 创建一个最小权限的 MinIO client Secret，键名为 `access-key` 和 `secret-key`，并在 Worker 配置中设置 `K8S_ADAPTER_OBJECT_STORAGE_SECRET_REF`。不要把 MinIO root Secret 直接引用给模型 Job，也不要把凭据写入 Tool Package 或镜像。

模型 Job 和执行 Worker 使用不同 namespace 的 Secret：Job 通过 `secretKeyRef` 读取 `sciminer-model-jobs/sciminer-minio-client`，Worker 自己通过环境变量读取 `sciminer-system/sciminer-execution-worker-secrets`。Worker 的 RBAC 不允许读取 Kubernetes Secret，因此不能让 Worker 在运行时跨 namespace 查询 MinIO 凭据。

先在 MinIO 中准备一个已授予目标 bucket 必要读写权限的 client 用户，然后创建两个 Secret。Worker 在集群内运行，数据库、Redis 和 MinIO 应使用 Service DNS，不能填 `localhost` 或 NodePort：

```bash
export DATABASE_URL="postgresql+asyncpg://scitool:${POSTGRES_PASSWORD}@sciminer-postgres.sciminer-system.svc.cluster.local:5432/scitool"
export REDIS_PASSWORD
export CELERY_BROKER_URL="redis://:${REDIS_PASSWORD}@sciminer-redis.sciminer-system.svc.cluster.local:6379/1"
export CELERY_RESULT_BACKEND="redis://:${REDIS_PASSWORD}@sciminer-redis.sciminer-system.svc.cluster.local:6379/2"
export MINIO_CLIENT_ACCESS_KEY='replace-with-minio-client'
export MINIO_CLIENT_SECRET_KEY='replace-with-minio-client-secret'
export JWT_SECRET_KEY="$(openssl rand -hex 32)"
export SETTINGS_ENCRYPTION_KEY="$(openssl rand -hex 32)"
export SSH_PASSWORD_REF_SSH_4090_ZHOUYC='set-only-if-ssh-password-auth-is-used'

kubectl -n sciminer-model-jobs create secret generic sciminer-minio-client \
  --from-literal=access-key="$MINIO_CLIENT_ACCESS_KEY" \
  --from-literal=secret-key="$MINIO_CLIENT_SECRET_KEY" \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl -n sciminer-system create secret generic sciminer-execution-worker-secrets \
  --from-literal=DATABASE_URL="$DATABASE_URL" \
  --from-literal=JWT_SECRET_KEY="$JWT_SECRET_KEY" \
  --from-literal=SETTINGS_ENCRYPTION_KEY="$SETTINGS_ENCRYPTION_KEY" \
  --from-literal=REDIS_PASSWORD="$REDIS_PASSWORD" \
  --from-literal=CELERY_BROKER_URL="$CELERY_BROKER_URL" \
  --from-literal=CELERY_RESULT_BACKEND="$CELERY_RESULT_BACKEND" \
  --from-literal=MINIO_ACCESS_KEY="$MINIO_CLIENT_ACCESS_KEY" \
  --from-literal=MINIO_SECRET_KEY="$MINIO_CLIENT_SECRET_KEY" \
  --from-literal=SSH_PASSWORD_REF_SSH_4090_ZHOUYC="$SSH_PASSWORD_REF_SSH_4090_ZHOUYC" \
  --dry-run=client -o yaml | kubectl apply -f -
```

平台会为 Job 注入：

```text
SCIMINER_OBJECT_STORAGE_ENDPOINT
SCIMINER_OBJECT_STORAGE_BUCKET
SCIMINER_OBJECT_STORAGE_ACCESS_KEY
SCIMINER_OBJECT_STORAGE_SECRET_KEY
SCIMINER_EXECUTION_OUTPUT_PREFIX=executions/<namespace>/<job-name>
SCIMINER_RESULT_OBJECT=executions/<namespace>/<job-name>/result.json
```

模型运行时必须先上传输出文件，再上传 `result.json`。`result.json` 遵循 `aidd.sciminer/result.v2`，文件路径相对于输出前缀，且声明的 SHA-256 必须与对象内容一致。Worker 会下载并校验所有对象，校验通过后才创建平台 File 记录和标准 ArtifactVersion。

`smoke-image` 已包含对象存储输入 staging 和输出上传逻辑，可以用于验证 Job 的对象存储链路；它仍不替代真实模型镜像的推理和产物契约验证。

## 4. 部署集群内执行 Worker

`execution-worker.example.yaml` 是显式启用模板，默认不在 `deploy/kubernetes/kustomization.yaml` 中。它只启动一个 Celery Worker，负责消费 `k8s_job` 任务并在集群内创建模型 Job；不会重启或修改当前宿主机上的 `8000` API，也不会修改 `backend/.env`。

该模板部署前必须完成两处替换：

1. 将 `registry.example.com/sciminer/backend@sha256:REPLACE_WITH_BACKEND_IMAGE_DIGEST` 替换为后端镜像的不可变 digest。
2. 如果 MinIO 不使用本目录的集群内 Service，替换 `MINIO_ENDPOINT` 和 `K8S_ADAPTER_OBJECT_STORAGE_ENDPOINT`。

确认占位符已经清空后，由管理员显式部署：

```bash
rg -n 'REPLACE_WITH|registry\.example\.com' deploy/kubernetes/execution-worker.example.yaml
kubectl apply -f deploy/kubernetes/execution-worker.example.yaml
kubectl -n sciminer-system rollout status deployment/sciminer-execution-worker
kubectl -n sciminer-system logs deployment/sciminer-execution-worker --tail=100
```

第一个 `rg` 命令应无输出。Worker 示例将 `EXECUTOR_ENABLED_K8S=true` 只注入这个集群内进程；当前宿主机 `8000` 已使用同一个 Celery broker，Worker 就绪后可消费 SSH 与 K8s 任务。管理员仍需显式选择 K8s ToolVersion 的 `k8s_job` 版本；SSH ToolVersion 不需要改成 K8s。

Worker 同时声明 `k8s_job` 和 `ssh_job` 能力，确保 Celery 模式下 SSH 默认版本仍可用；`EXECUTOR_ENABLED_SSH=true` 不会把 SSH 版本切换成 K8s。正式生产环境应为 API、Celery Worker、数据库、Redis 和 MinIO 分别准备可审计的镜像、Secret 和网络策略。

回滚本示例时只需缩容或删除该 Worker，不要删除成功任务产生的数据库记录和 MinIO 对象：

```bash
kubectl -n sciminer-system scale deployment/sciminer-execution-worker --replicas=0
kubectl -n sciminer-system delete deployment/sciminer-execution-worker \
  configmap/sciminer-execution-worker-config
```

## 5. 构建 smoke image

Worker 与 API 共用 `backend/Dockerfile` 的 `production` 阶段，Worker 仅通过 Kubernetes `command/args` 覆盖为 Celery 进程，不需要单独维护一份运行时依赖。请在 Docker daemon 可用且能够访问开发 Registry 的构建机上执行：

```bash
cd backend
export IMAGE_REPOSITORY='<K3S节点IP>:30500/sciminer/backend'
export IMAGE_VERSION='worker-20261008'
docker build --target production -t "$IMAGE_REPOSITORY:$IMAGE_VERSION" .
docker push "$IMAGE_REPOSITORY:$IMAGE_VERSION"
docker inspect --format '{{index .RepoDigests 0}}' "$IMAGE_REPOSITORY:$IMAGE_VERSION"
```

将 `docker inspect` 输出的完整 digest 写入 Worker 清单。若构建机使用 Podman，连接当前开发用 HTTP Registry 时使用 `podman push --tls-verify=false`；生产环境应改用 TLS Registry。

Smoke 镜像仍按以下命令单独构建：

```bash
export IMAGE_REPOSITORY='registry.example/sciminer/k8s-smoke'
export IMAGE_VERSION='0.1.0'
docker build \
  -f deploy/kubernetes/smoke-image/Dockerfile \
  -t "$IMAGE_REPOSITORY:$IMAGE_VERSION" \
  deploy/kubernetes/smoke-image
docker push "$IMAGE_REPOSITORY:$IMAGE_VERSION"
docker inspect --format '{{index .RepoDigests 0}}' "$IMAGE_REPOSITORY:$IMAGE_VERSION"
```

将输出的完整 `@sha256:<digest>` 记录到 smoke Job 或 ToolVersion 配置中。不要把 `latest` 或普通可变 tag 注册为 `k8s_job` 运行镜像。

如果集群无法访问私有仓库，需要在模型 Job namespace 创建 image pull Secret，并由平台执行环境配置引用它：

```bash
kubectl -n sciminer-model-jobs create secret docker-registry sciminer-registry \
  --docker-server='<registry-host>' \
  --docker-username='<registry-user>' \
  --docker-password='<registry-password>' \
  --dry-run=client -o yaml | kubectl apply -f -
```

## 6. 部署前检查

```bash
kubectl get nodes -o wide
kubectl get storageclass
kubectl -n sciminer-model-jobs auth can-i create jobs \
  --as=system:serviceaccount:sciminer-system:sciminer-execution-worker
kubectl -n sciminer-model-jobs auth can-i get pods/log \
  --as=system:serviceaccount:sciminer-system:sciminer-execution-worker
kubectl -n sciminer-model-jobs auth can-i get secrets \
  --as=system:serviceaccount:sciminer-system:sciminer-execution-worker
```

最后一条应返回 `no`。在执行 Worker 示例清单完成镜像、数据库、Redis、MinIO 和 Secret 配置前，不要部署它；当前宿主机 API 继续保持 `EXECUTOR_ENABLED_K8S=false`。不要只因为 namespace 和 RBAC 已创建就开启任务调度。
