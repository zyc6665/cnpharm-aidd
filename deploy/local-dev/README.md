# 本地开发环境（Windows 平台机 + 4090 计算节点）

> 状态：2026-11-07 重置后生效。开发迭代阶段定稿：**平台侧数据服务用 docker 容器，不用本地 k8s**。

## 1. 拓扑

```
Windows（平台部署机）
  docker 容器（--restart unless-stopped）
    cnpharm-pg     127.0.0.1:30432 -> 5432   postgres:16-alpine   volume cnpharm-pg-data
    cnpharm-redis  127.0.0.1:30379 -> 6379   redis:7-alpine      volume cnpharm-redis-data
    cnpharm-minio  127.0.0.1:30900 -> 9000   minio RELEASE.2024-06-13T22-53-53Z
                   127.0.0.1:30901 -> 9001   volume cnpharm-minio-data
  本机进程
    uvicorn  app.main:app    127.0.0.1:8000
    celery worker            队列 default,high_priority,gpu_queue,heavy_compute,cpu_queue,tool_tasks,maintenance
    celery beat
    vite dev                 127.0.0.1:5173

4090（纯计算节点，k3s）
  sciminer-storage ns:  registry:30500 + PVC sciminer-registry-data(40Gi)   ← 唯一保留的镜像落点
  cnpharm-aidd ns:      空命名空间 + ServiceAccount model-runner（供 Job 提交）
  hostPath 权重缓存:    /data/zhouyc/model-cache/...、/data/zhouyc/k8s-model-build/...
```

## 2. 为什么本地数据服务不用 k8s

Docker Desktop 的 k8s 跑在 WSL2 虚拟机的独立网络命名空间里，NodePort 只在 `172.19.0.x` 内部监听，
Windows 主机没有对应端口（实测 `127.0.0.1:30432/30379` 全部不可达，`curl localhost:30900` 也不通）。
Docker Desktop 只转发**容器 publish 的端口**，不转发 k8s NodePort。

4090 那侧没有这个问题：k3s 装在物理机上，Pod 就绪后 `30432/30379` 从 Windows 直连可用。

### 将来要本地也走真 k8s

Windows 11 25H2 + WSL 2.5.10 已满足前提，写 `%USERPROFILE%\.wslconfig`：

```ini
[wsl2]
networkingMode=mirrored
dnsTunneling=true
autoProxy=true
```

`wsl --shutdown` 后重启 Docker Desktop，NodePort 即可从 `127.0.0.1` 访问。
届时把 `deploy/k8s-dev/cnpharm-aidd/10-data-services.yaml` 重新 apply，替换掉 docker 容器。

## 3. 关键环境变量（backend/.env）

| 变量 | 值 | 备注 |
|---|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://scitool:***@127.0.0.1:30432/scitool` | 本地 docker PG |
| `REDIS_HOST` / `REDIS_PORT` | `127.0.0.1` / `30379` | 本地 docker Redis |
| `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND` | `redis://:***@127.0.0.1:30379/0` `/1` | 同上 |
| `MINIO_ENDPOINT` | `127.0.0.1:30900` | 平台自身读写 |
| `K8S_ADAPTER_NAMESPACE` | `cnpharm-aidd` | 计算 Job 落点（4090 侧） |
| `K8S_ADAPTER_OBJECT_STORAGE_ENDPOINT` | `http://10.4.3.19:30900` | **供 4090 上的 Pod 回写产物**；不能用 127.0.0.1 |

最后一条最容易漏：计算 Pod 在 4090 上，`127.0.0.1` 指的是 4090 自己。当前 Windows 侧只有
`10.4.3.19` 这个地址对 4090 可达（另外两块网卡实测不通）；换机器/换网段时要重新确认。

## 4. 起停

```powershell
# 数据服务
docker start cnpharm-pg cnpharm-redis cnpharm-minio
docker ps --format "{{.Names}} | {{.Status}}"

# MOUNT 前先确认端口
foreach ($p in 30432,30379,30900) { "$p => " + (Test-NetConnection 127.0.0.1 -Port $p -InformationLevel Quiet) }

# 应用
cd backend;  E:\anaconda\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
cd backend;  E:\anaconda\python.exe -m celery -A app.worker.celery_app worker --loglevel=info --pool=solo -Q default,high_priority,gpu_queue,heavy_compute,cpu_queue,tool_tasks,maintenance
cd backend;  E:\anaconda\python.exe -m celery -A app.worker.celery_app beat --loglevel=info
cd frontend; npm run dev -- --host 127.0.0.1 --port 5173
```

健康检查应全部 healthy（含 `celery`）：`GET http://127.0.0.1:8000/api/v1/system/health`

## 5. 凭据

- 平台账号：`admin` / 见 `backend/.env` 或本地私密记录
- PG / Redis / MinIO 凭据：`backend/.env`（未入库），k8s 侧的 Secret 名为 `cnpharm-aidd-credentials`
- 旧 4090 库备份（重置前）：`/data/zhouyc/backup-4090-db-20261107.sql.gz`
