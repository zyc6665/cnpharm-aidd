# Pocket2Mol 镜像：完整构建与适配层增量构建

本目录有两种构建方式：

| 文件 | 用途 | 耗时 |
|---|---|---|
| `Dockerfile` | 完整镜像：conda 环境 + 模型代码 + 权重 | 十几分钟 |
| `Dockerfile.adaptor` | 只替换 `platform_adaptor/`（后处理脚本） | 几秒 |

`Dockerfile` 没有改动，仍按原方式构建。日常只改「结果后处理」时用增量方式，
避免为了一个脚本重建整包。

## 前置条件（在 4090 服务器上）

- 已有完整镜像并推送到内网 registry，例如
  `127.0.0.1:30500/aidd/compute-pocket2mol@sha256:82481106...`。
- 能访问该 registry（`docker login 127.0.0.1:30500`，如需要）。
- 构建上下文是 `deploy/kubernetes/model-image-template/`，因为适配层目录就在它下面。

## 增量构建

在仓库根目录执行（把 `<base-digest>` 换成当前完整镜像的 digest）：

```bash
docker build \
  -f deploy/model-images/k8s/pocket2mol/Dockerfile.adaptor \
  --build-arg BASE_IMAGE=127.0.0.1:30500/aidd/compute-pocket2mol@sha256:<base-digest> \
  -t 127.0.0.1:30500/aidd/compute-pocket2mol:adaptor-$(git rev-parse --short HEAD) \
  deploy/kubernetes/model-image-template
```

默认 `BASE_IMAGE` 已写死在 `Dockerfile.adaptor` 里，不传 `--build-arg` 也能构建。

## 容器内冒烟验证

后处理依赖镜像里已有的 RDKit。用一个最小目录模拟模型产物：

```bash
docker run --rm --entrypoint /bin/bash \
  127.0.0.1:30500/aidd/compute-pocket2mol:adaptor-<rev> -lc '
set -e
work=$(mktemp -d)
mkdir -p "$work/artifacts"
cat > "$work/artifacts/SMILES.txt" <<EOF
CC(=O)Oc1ccccc1C(=O)O
CCO
EOF
echo "dummy" > "$work/artifacts/generated_molecules.sdf"
cat > "$work/result.json" <<EOF
{"success": true, "outputs": {"smiles_file": "artifacts/SMILES.txt", "combined_sdf": "artifacts/generated_molecules.sdf"}}
EOF
/opt/conda/bin/python /opt/aidd/platform_adaptor/postprocess_result.py \
  --model pocket2mol --output-dir "$work" --task-id smoke
head -1 "$work/artifacts/generated_molecules.csv"
python - "$work/artifacts/generated_molecules.csv" <<PY
import csv, sys
rows = list(csv.DictReader(open(sys.argv[1], encoding="utf-8")))
assert rows and rows[0]["molecular_weight"], "missing descriptors"
assert rows[0]["scaffold"], "missing Murcko scaffold"
assert all(r["smiles"] for r in rows), "missing smiles column"
print("postprocess smoke OK:", len(rows), "rows")
PY
'
```

期望输出首行为
`smiles,molecular_weight,logp,hbd,hba,tpsa,rotatable_bonds,qed,lipinski_violations,scaffold`，
并打印 `postprocess smoke OK: 2 rows`。

## 推送并记录新 digest

```bash
docker push 127.0.0.1:30500/aidd/compute-pocket2mol:adaptor-<rev>
docker image inspect 127.0.0.1:30500/aidd/compute-pocket2mol:adaptor-<rev> \
  --format '{{index .RepoDigests 0}}'
```

把输出的 `@sha256:...` 记下来。`backend/app/execution/adapters/kubernetes_manifest.py`
要求镜像以 digest 引用（`docs/07 §3.6`）：更新平台里的 pocket2mol 镜像引用属于
**契约/部署层改动**，需要由 P1 单独提迁移 PR，不要混进本目录的适配层改动。
