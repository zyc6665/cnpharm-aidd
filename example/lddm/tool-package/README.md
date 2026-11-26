# LDDM Tool Package v2

将 `LPDI-EPFL/lddm` 口袋条件 3D 分子生成模型封装为平台标准 `ToolPackage v2` 交付包。

- 标准输入：`protein_pdb`（`protein_structure@1`，必填）与 `pocket`（`binding_pocket@1`，可选；也可由 `center_x/y/z` 指定）
- 标准输出：`molecules`（`molecule_table@1`，含 9 项 RDKit 理化描述符与 Murcko 骨架）、`ligands`（`ligand_structure@1`）、`report`（`run_report@1`）
- 运行形态：`k8s_job`，`lddm.ckpt` 已随镜像打包，无需宿主机外挂权重目录。

## 模板定位与镜像替换说明

仓库里的 `tool.yaml` 是**离线合规参考模板**：`registry.example/aidd/compute-lddm`、`fallback.sha256`（全 0 占位）与 `validation_status: unvalidated` 用于避免在源码库写入内网真实 IP。在目标集群（如 4090 `10.202.2.228:30500`）部署导入前，需将 `variants[].image` 与 `runtime.artifacts.primary.image` 替换为集群仓库中已推送镜像的 `sha256` digest 引用（如 `10.202.2.228:30500/aidd/compute-lddm@sha256:6fc5496e4e27b424f1042be19a6166a14739ae0434845bee21466d2031b889b6`）。

## 新环境导入 → Smoke → 激活发布流程

`lddm-pocket-ligand-generation` 未写入 `platform_tool_seeding.py` 的启动必备清单，新环境需通过 ToolPackage v2 流程导入并激活：

1. **导入 Tool Package**：`POST /api/v1/tool-packages`（提交替换真实镜像地址后的 manifest 与签名）。
2. **发布 Tool Package**：`POST /api/v1/tool-packages/{package_id}/publish`。
3. **注册 K8s 候选版本**：`POST /api/v1/tool-packages/{package_id}/kubernetes-registrations`（选 `variant_name: "nvidia-cuda"`、`resource_profile: "gpu-large"`、分类 `molecule_generation`），此时工具版本为候选态（`is_active=false`）。
4. **冒烟验证**：`POST /api/v1/tools/{tool_id}/versions/{version_id}/smoke`，确认测试 Job 成功通过。
5. **提升激活并公开工具**：`POST /api/v1/tools/{tool_id}/versions/{version_id}/promote` 将版本激活为 `current_version_id`，并将工具发布为 `published` 公开可见。
