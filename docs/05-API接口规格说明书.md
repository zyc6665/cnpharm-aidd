# 中国医药 AI 药物研发平台 · API 接口规格说明书

| 项 | 内容 |
|---|---|
| 文档编号 | DRP-API-v1.2 |
| 文档版本 | **v1.2**（2026-10-23 生产级复审补齐；此前 v1.1 于 2026-10-20 架构评审修订，变更明细见 `03A`） |
| 上游 | `03-系统架构设计说明书.md`、`04-数据模型设计说明书.md` |
| 风格 | RESTful + JSON，部分计算提交采用动词式资源操作 |

---

## 1. 通用约定

### 1.1 基础信息

| 项 | 约定 |
|---|---|
| 前缀 | `/api/v1` |
| 协议 | HTTPS（内网证书） |
| 编码 | UTF-8，`Content-Type: application/json;charset=UTF-8` |
| 认证 | `Authorization: Bearer <JWT>` |
| 幂等 | 写操作支持 `X-Idempotency-Key`（**创建类 POST 必填**：任务提交、启动工作流、批量预测、批量筛选、MD 计算、创建分片上传会话；GET 与天然幂等的 PUT 不需要） |
| 时间格式 | ISO 8601，时区 `Asia/Shanghai` |
| 追踪 | `X-Request-Id`（服务端生成并回传，写入日志） |

### 1.2 统一响应体

```json
{
  "code": 0,
  "message": "OK",
  "data": {},
  "requestId": "req_01J...",
  "timestamp": "2026-07-01T10:00:00+08:00"
}
```

失败：

```json
{
  "code": 40401,
  "message": "项目不存在或无权访问",
  "data": null,
  "requestId": "req_01J...",
  "timestamp": "2026-07-01T10:00:00+08:00"
}
```

### 1.3 错误码

| 区间 | 类别 | 示例 |
|---|---|---|
| 0 | 成功 | |
| 400xx | 参数与校验 | `40001` 参数缺失、`40002` 参数非法、`40003` 文件格式不支持 |
| 401xx | 认证 | `40101` 未登录、`40102` Token 过期 |
| 403xx | 权限 | `40301` 无项目权限、`40302` 只读成员不可写、`40303` 配额不足 |
| 404xx | 资源不存在 | `40401` 项目不存在、`40402` 任务不存在 |
| 409xx | 状态冲突 | `40901` 资源已存在 / 项目已归档（**两义，用 `detail.reason` 区分**：`DUPLICATE` 表示唯一约束冲突、`ARCHIVED` 表示项目已归档；见 `04` §5.6）、`40902` 任务当前状态不允许该操作、`40903` 乐观锁版本冲突（带 `currentVersion`）、`40904` 幂等键正在处理中（带 `Retry-After: 2`）、`40905` 幂等键已用于另一请求（同 key 不同请求体） |
| 422xx | 业务规则 | `42201` 序列长度超限、`42202` 候选集合为空、`42203` 导入数据全部失败、`42204` 分片不完整（缺片或编号不连续）、`42205` 校验和不匹配（`sha256` 与声明不符，对象已标记删除）、`42206` 不能移除最后一个负责人 |
| 429xx | 限流 | `42901` 提交过于频繁、`42902` 并发任务超限 |
| 500xx | 服务端 | `50001` 内部错误、`50002` 依赖服务不可用 |
| 503xx | 可用性 / 内部 | `50301` 无可用 DCU，进入排队（非错误，配合 `queued=true`）、`50302` 数据库行锁等待超时（`LOCK_TIMEOUT`，见 `04` §5.6）、`50303` 内部错误（**未分类异常兜底码**，`detail.requestId` 必填，供运维按 `14` §5 定位） |

### 1.4 分页

请求：`?page=1&size=20&sortBy=createdAt&order=desc`
响应：

```json
{
  "items": [],
  "page": 1,
  "size": 20,
  "total": 137,
  "totalPages": 7
}
```

默认 `size=20`，最大 `200`。

### 1.5 异步任务约定

提交类接口同步返回 `{ "taskId": "...", "status": "QUEUED", "queuePosition": 3 }`，业务侧通过：

- `GET /api/v1/tasks/{taskId}` 轮询，或
- `GET /api/v1/tasks/{taskId}/events`（SSE）订阅状态与进度

---

## 2. 认证与权限

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v1/auth/login` | 登录，返回 access/refresh token |
| POST | `/api/v1/auth/refresh` | 刷新 token |
| POST | `/api/v1/auth/logout` | 登出 |
| GET | `/api/v1/auth/me` | 当前用户信息与全局角色 |
| GET | `/api/v1/users` | 用户列表（管理员，需 `user.read`） |
| POST | `/api/v1/users` | 创建用户（管理员，需 `user.write`）；body `{username, displayName, email?, password?, authSource, role}`；`password` 缺省时由服务端生成临时口令并在响应中一次性返回，同时置 `mustChangePassword=true` |
| PUT | `/api/v1/users/{id}` | 更新显示名 / 邮箱 / 系统角色（`ADMIN`↔`USER`，需 `user.write`）；**`sys_user_role` 的增删只能经此接口**，不提供独立接口（`04` §5.0） |
| PUT | `/api/v1/users/{id}/status` | 启停用户（`ACTIVE`/`DISABLED`，需 `user.write`） |
| POST | `/api/v1/users/{id}:reset-password` | **管理员重置本地用户口令**（需 `user.reset_password`）；body `{tempPassword?}`，缺省由服务端生成；返回 `{tempPassword, mustChangePassword:true}`；置 `password_reset_by` 并写 `audit_log.action=PASSWORD_RESET`；**LDAP 用户返回 `40002`**（口令由目录服务管理） |
| POST | `/api/v1/auth/change-password` | **用户自助改密**；body `{oldPassword, newPassword}`；成功后置 `must_change_password=false`、更新 `password_updated_at`，并**吊销该用户全部 refresh token**（Redis `jti` 黑名单）；`oldPassword` 错误返回 `40101` |

> **v1.2 补齐说明**：此前只有「创建/启停」，`16` §14.1 却承诺「重置密码」，导致开发无处落接口。现补 `:reset-password` 与 `auth/change-password` 两个动作，并在 `04` §5.0 补 `must_change_password` / `password_reset_by` 两个字段。**口令一律不落明文、不由服务端回显历史口令**；临时口令只在创建/重置的响应中出现一次。

---

## 3. 项目与成员（M1）

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v1/projects` | 创建项目 |
| GET | `/api/v1/projects` | 项目列表（分页 + 关键字 + 状态筛选） |
| GET | `/api/v1/projects/{id}` | 项目详情 |
| PUT | `/api/v1/projects/{id}` | 更新项目 |
| POST | `/api/v1/projects/{id}/archive` | 归档（归档后只读） |
| DELETE | `/api/v1/projects/{id}` | 软删除 |
| GET | `/api/v1/projects/{id}/overview` | 项目总览（资产/任务/结果统计） |
| GET | `/api/v1/projects/{id}/members` | 成员列表 |
| POST | `/api/v1/projects/{id}/members` | 添加成员 |
| PUT | `/api/v1/projects/{id}/members/{userId}` | 修改成员角色；**改为 `OWNER` 时同一事务内同步 `project.owner_id`**（`04` §5.1 一致性规则 3） |
| DELETE | `/api/v1/projects/{id}/members/{userId}` | 移除成员；**不得移除最后一个 `OWNER`**，否则 `42206`（`04` §5.1 一致性规则 4） |
| GET/PUT | `/api/v1/projects/{id}/quota` | 查询/设置项目算力配额（**v1.1**：口径为算力分钟，字段 `dailyQuotaMinutes` / `quotaPeriod` / `overdraftRatio`，见 `04` §5.3） |
| GET | `/api/v1/projects/{id}/stage` | **研发阶段与缺口（v1.1 新增）**，见 §3.2 |
| GET | `/api/v1/projects/{id}/decisions` | **决策记录列表（v1.1 新增）**，见 §3.3 |
| POST | `/api/v1/projects/{id}/decisions` | **提交决策（v1.1 新增）** |

### 3.1 创建项目

**POST** `/api/v1/projects`

```json
{
  "name": "KRAS G12C 抑制剂研发",
  "code": "PRJ-2026-KRAS",
  "description": "针对 KRAS G12C 靶点的候选物发现",
  "targetIds": [],
  "members": [{ "userId": "usr_...", "role": "MEMBER" }]
}
```

响应 `data`：`{ "id": "prj_...", "status": "ACTIVE", "createdAt": "..." }`

### 3.2 研发阶段与缺口（v1.1 新增）

**GET** `/api/v1/projects/{id}/stage`

响应 `data`：

```json
{
  "currentStage": "S2",
  "stageName": "结构与口袋就绪",
  "reachedStages": ["S0", "S1", "S2"],
  "nextStage": "S3",
  "gaps": [
    { "code": "NO_POCKET_SELECTED", "message": "已有 3 个结构，但尚未选定口袋",
      "action": "前往结构详情选择口袋", "link": "/projects/prj_x/targets/tgt_y/structures/stu_z" }
  ],
  "stageReachedAt": { "S0": "2026-09-01T10:00:00Z", "S1": "...", "S2": "..." }
}
```

**设计约束**：
- 该接口是**纯推导**（只读），不引入 `project.stage` 字段，避免阶段与真实数据不一致。
- 阶段可回退；回退不返回错误，仅在 `reachedStages` 中如实反映。
- `gaps` 最多返回 5 条，按阻塞程度排序。

### 3.3 决策记录（v1.1 新增）

**POST** `/api/v1/projects/{id}/decisions`

```json
{
  "decisionPoint": "DP3",
  "subjectType": "CANDIDATE_SET",
  "subjectId": "set_...",
  "selectedIds": ["cand_a", "cand_b"],
  "excludedIds": ["cand_c"],
  "basisTaskIds": ["tsk_...", "tsk_..."],
  "basisMetrics": { "avgDockingScore": -8.2, "admetPassRate": 0.73 },
  "reason": "亲和力与成药性均达标，且骨架多样性好",
  "snapshot": [
    { "candidateId": "cand_a", "score": -9.1, "rank": 1 }
  ]
}
```

响应 `data`：`{ "id": "dec_...", "createdAt": "..." }`

**约束**：
- `snapshot` **必填**，由前端提交时从当前结果页快照，服务端校验每个 `candidateId` 均属于 `subjectId`。
- 决策记录**只能新增，不能修改与删除**（与 `audit_log` 同级别）。
- 需项目角色 ≥ `MEMBER`；`VIEWER` 返回 403xx。

---

## 4. 数据资产与导入导出（M1）

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v1/projects/{id}/datasets:import` | 批量导入（异步，返回 taskId） |
| GET | `/api/v1/projects/{id}/datasets` | 数据集列表 |
| GET | `/api/v1/datasets/{id}` | 数据集详情（含导入结果统计） |
| DELETE | `/api/v1/datasets/{id}` | 删除数据集 |
| POST | `/api/v1/datasets:export` | 导出（异步，返回 taskId） |
| GET | `/api/v1/projects/{id}/compounds` | 化合物列表（支持属性筛选与排序） |
| POST | `/api/v1/projects/{id}/compounds` | 单个新增化合物 |
| GET | `/api/v1/compounds/{id}` | 化合物详情（含属性与 2D 结构） |
| GET | `/api/v1/compounds/{id}/versions` | 版本历史 |
| GET | `/api/v1/compounds/{id}/diff` | 版本差异对比（`?from=1&to=3`） |
| POST | `/api/v1/search/mol` | 分子检索（子结构/相似性/指纹） |
| GET | `/api/v1/assets/{urn}/presign` | 获取文件预签名下载 URL |
| POST | `/api/v1/uploads` | **创建分片上传会话**（v1.2 新增，见 §4.2）；必填 `X-Idempotency-Key` |
| PUT | `/api/v1/uploads/{id}/parts/{partNumber}` | **上报一个已完成分片**（v1.2 新增） |
| POST | `/api/v1/uploads/{id}:complete` | **合并分片并结束会话**（v1.2 新增）；返回最终 URN |
| DELETE | `/api/v1/uploads/{id}` | 取消上传（置 `ABORTED` 并调 MinIO `AbortMultipartUpload`） |

### 4.1 批量导入

**POST** `/api/v1/projects/{id}/datasets:import`
`Content-Type: multipart/form-data`（大文件走预签名直传，此处传 URN）

```json
{
  "datasetName": "化合物库 2026Q3",
  "datasetType": "COMPOUND",
  "fileUrn": "oss://drp-assets/prj_x1/compound/20260701/u.sdf",
  "fileType": "SDF",
  "fieldMapping": { "MW": "mol_weight", "SMILES": "canonical_smiles" },
  "dedupeStrategy": "INCHIKEY_UPDATE",
  "onError": "SKIP_AND_CONTINUE"
}
```

响应：

```json
{ "taskId": "tsk_...", "status": "QUEUED" }
```

导入完成后 `GET /api/v1/tasks/{taskId}` 返回：

```json
{
  "status": "SUCCEEDED",
  "progress": 100,
  "summary": { "total": 1000, "success": 996, "failed": 4, "duplicate": 12 },
  "errorReportUrn": "oss://drp-results/prj_x1/task/tsk_.../import_errors.csv"
}
```

### 4.2 分片上传（**v1.2 新增**）

> **为什么补**：`04` §13.2 要求 `>100MB` 强制 Multipart，`04` §5.8 也定义了 `upload_session` 表，但**此前一个接口都没有**——表建了没人写。前端只知道「大文件走预签名直传」，不知道怎么开始、怎么续传、怎么结束。

**① 创建会话** `POST /api/v1/uploads`（必填 `X-Idempotency-Key`）

```json
{
  "projectId": "prj_x1",
  "filename": "compound_lib_2026Q3.sdf",
  "size": 1073741824,
  "contentType": "chemical/x-mdl-sdfile",
  "sha256": "d3f1...（可选，客户端预先算好则服务端合并时校验）"
}
```

响应：

```json
{
  "uploadId": "ups_01J...",
  "objectKey": "prj_x1/upload/20261023/compound_lib_2026Q3.sdf",
  "partSize": 16777216,
  "partCount": 64,
  "expiresAt": "2026-10-24T10:00:00Z"
}
```

约定：`partSize` 由服务端决定（默认 16MB，最后一片可小于该值）；`partCount = ceil(size / partSize)`，上限 2GB → ≤ 128 片；会话 24 小时过期。

**② 上报分片** `PUT /api/v1/uploads/{id}/parts/{partNumber}`

请求体为该分片的原始字节（`Content-Type: application/octet-stream`，带 `Content-MD5` 可选）。服务端直通 MinIO `UploadPart`，成功后把 `{partNumber, etag, size}` 追加进 `upload_session.parts`（追加方式见 `04` §5.6「例外与补充」——**禁止整列覆盖写**）。

响应：`{ "partNumber": 3, "etag": ""a1b2..."", "received": true }`

**③ 合并结束** `POST /api/v1/uploads/{id}:complete`

```json
{ "parts": [{"partNumber": 1, "etag": ""a1b2...""}, {"partNumber": 2, "etag": ""...""}] }
```

响应：

```json
{ "urn": "oss://drp-assets/prj_x1/upload/20261023/compound_lib_2026Q3.sdf", "size": 1073741824, "sha256": "d3f1..." }
```

校验：`parts` 覆盖 `1..partCount` 且无缺片，否则 `42204`（分片不完整）；服务端算出的 `sha256` 与创建时声明不符 → `42205`（校验和不匹配），对象标记删除。成功后会话置 `COMPLETED`，返回的 `urn` 可直接用于 §4.1 导入的 `fileUrn`。

**④ 取消** `DELETE /api/v1/uploads/{id}` → 置 `ABORTED` 并调 MinIO `AbortMultipartUpload`。

**断点续传**：`GET /api/v1/uploads/{id}` 返回 `parts` 已完成列表，前端据此只重传缺失分片。

---

## 5. 靶点与结构分析（M2）

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v1/projects/{id}/targets` | 创建靶点 |
| GET | `/api/v1/projects/{id}/targets` | 靶点列表 |
| GET | `/api/v1/targets/{id}` | 靶点详情（含蛋白与结构概览） |
| PUT/DELETE | `/api/v1/targets/{id}` | 更新/删除 |
| POST | `/api/v1/targets/{id}/proteins` | 导入蛋白序列或结构 |
| GET | `/api/v1/proteins/{id}` | 蛋白详情（序列 + 结构列表） |
| POST | `/api/v1/proteins/{id}/structures:predict` | ★ 提交结构预测任务 |
| POST | `/api/v1/proteins/{id}/structures:import` | 导入已有结构 |
| GET | `/api/v1/proteins/{id}/structures` | 结构列表 |
| GET | `/api/v1/structures/{id}` | 结构详情（含 pLDDT、文件 URN） |
| POST | `/api/v1/structures/{id}:prepare` | 结构准备（生成 PDB/PDBQT） |
| POST | `/api/v1/structures/{id}/pockets:predict` | ★ 提交口袋预测任务 |
| GET | `/api/v1/structures/{id}/pockets` | 口袋列表（按评分排序） |
| POST | `/api/v1/pockets/{id}:select` | 选定口袋（作为设计与对接约束） |
| GET | `/api/v1/pockets/{id}/residues` | 口袋残基列表（含关键残基标记） |
| GET | `/api/v1/structures/{id}/pdb` | 获取结构文件内容（或预签名 URL） |
| POST | `/api/v1/structures/{id}:export` | 导出结构、位点与分析结果 |

### 5.1 ★ 提交结构预测

**POST** `/api/v1/proteins/{id}/structures:predict`

```json
{
  "modelRef": { "name": "boltz-2", "version": "2.0.1" },
  "params": { "useMsa": false, "numRecycles": 3, "seed": 20260101 },
  "scale": { "kind": "SINGLE", "itemCount": 1 },
  "resourceProfile": { "dcu": 1, "cpu": 8, "memGB": 32 },
  "priority": "NORMAL"
}
```

> **v1.1 修订**：原示例写 `esmfold:1.0.3`（未经 K100-AI 验证，且不在已定型清单内），已改为 `boltz-2:2.0.1`（`03` D-06）。同时按 `03` §5.2.2 新增 `scale` 字段（由 `drp-scheduler` 校核，客户端值仅作预估）。`resourceProfile` 同样仅作预估与上限保护，准入时按规模重算（`04` §9）。

响应：`{ "taskId": "tsk_...", "status": "QUEUED", "queuePosition": 2, "estimatedWaitSeconds": 120 }`

### 5.2 ★ 口袋预测结果

**GET** `/api/v1/structures/{id}/pockets`

```json
{
  "items": [
    {
      "id": "pkt_...",
      "rank": 1,
      "score": 18.42,
      "volume": 1240.5,
      "center": { "x": 12.3, "y": -4.1, "z": 8.9 },
      "boxSize": { "x": 22.5, "y": 22.5, "z": 22.5 },
      "residueCount": 27,
      "selected": true,
      "tool": { "name": "lvpocket", "version": "2.0.0" }
    }
  ]
}
```

---

## 6. 分子与多肽设计（M3）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v1/models` | 可用模型列表（`?capability=MOLECULE_GENERATION`） |
| GET | `/api/v1/models/{name}/versions/{version}/schema` | 模型参数 Schema（驱动动态表单） |
| POST | `/api/v1/design/molecules:generate` | ★ 小分子生成 |
| POST | `/api/v1/design/peptides:generate` | ★ 多肽设计 |
| GET | `/api/v1/tasks/{taskId}/results` | 生成结果列表（分页 + 按评分排序） |
| POST | `/api/v1/projects/{id}/candidate-sets` | 创建候选集合 |
| POST | `/api/v1/candidate-sets/{id}/items` | 批量加入候选物 |
| GET | `/api/v1/projects/{id}/candidate-sets` | 候选集合列表 |
| GET | `/api/v1/candidate-sets/{id}/items` | 集合内候选物（支持筛选/排序） |
| GET | `/api/v1/candidates/{id}` | 候选物详情（结构/序列 + 属性 + 已有结果） |
| POST | `/api/v1/candidates:compare` | 多候选物比较（`{"candidateIds":[...]}` ≤ 6） |
| POST | `/api/v1/candidate-sets/{id}:export` | 导出候选集合 |

### 6.1 ★ 小分子生成

**POST** `/api/v1/design/molecules:generate`

```json
{
  "projectId": "prj_...",
  "targetId": "tar_...",
  "structureId": "str_...",
  "pocketId": "pkt_...",
  "modelRef": { "name": "std-diff", "version": "1.0.0" },
  "params": {
    "numMolecules": 200,
    "molWeightRange": [300, 600],
    "logPRange": [1, 4],
    "requiredSubstructure": "",
    "seed": 20260101
  },
  "saveToSetId": "cset_...",
  "priority": "NORMAL"
}
```

响应：`{ "taskId": "tsk_...", "status": "QUEUED" }`

完成后结果：

```json
{
  "generated": 200,
  "valid": 187,
  "duplicated": 9,
  "items": [
    { "candidateId": "cand_...", "smiles": "...", "designScore": 0.87,
      "props": { "molWeight": 432.5, "logP": 2.31, "qed": 0.71 } }
  ]
}
```

---

## 7. 性质预测（M4）

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v1/predict/affinity` | ★ 亲和力预测（单个） |
| POST | `/api/v1/predict/admet` | ★ ADMET 预测（单个） |
| POST | `/api/v1/predict/batch` | ★ 批量预测（`affinity` + `admet` 指标组） |
| GET | `/api/v1/candidates/{id}/predictions` | 候选物的预测结果（按指标组） |
| GET | `/api/v1/tasks/{taskId}/predictions` | 某任务的全部预测结果（可筛选/排序） |
| POST | `/api/v1/predictions:export` | 导出预测指标与结果 |
| GET | `/api/v1/predict/metrics` | 支持的指标字典（key/中文名/单位/阈值/方向） |

### 7.1 ★ 批量预测

**POST** `/api/v1/predict/batch`

```json
{
  "projectId": "prj_...",
  "source": { "type": "CANDIDATE_SET", "setId": "cset_..." },
  "metricGroups": ["ADMET", "AFFINITY"],
  "structureId": "str_...",
  "pocketId": "pkt_...",
  "modelRefs": [
    { "capability": "ADMET_PREDICTION", "name": "molp-pc", "version": "1.0.0" },
    { "capability": "AFFINITY_PREDICTION", "name": "msign", "version": "1.0.0" }
  ],
  "shardSize": 50,
  "priority": "BULK"
}
```

响应：`{ "taskId": "tsk_...", "shardCount": 10, "status": "QUEUED" }`

---

## 8. 虚拟筛选与计算评估（M5）

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v1/screen/conformers` | 构象分析 |
| POST | `/api/v1/screen/pharmacophore` | 药效团匹配 |
| POST | `/api/v1/screen/docking` | 分子对接（单个或集合） |
| POST | `/api/v1/screen/virtual-screening` | ★ 批量虚拟筛选（漏斗流水线） |
| GET | `/api/v1/tasks/{taskId}/screening` | 筛选结果（按 finalRank 排序，支持阈值过滤） |
| GET | `/api/v1/docking-results/{id}` | 对接结果详情（姿势 + 相互作用） |
| POST | `/api/v1/md/simulate` | 分子动力学计算 |
| GET | `/api/v1/tasks/{taskId}/md` | MD 结果（轨迹 URN + RMSD/RMSF 曲线） |
| POST | `/api/v1/md/free-energy` | 结合自由能评估 |
| GET | `/api/v1/tasks/{taskId}/free-energy` | 自由能结果（含能量分解） |
| POST | `/api/v1/screen/results:compare` | 多候选物计算结果比较 |
| POST | `/api/v1/tasks/{taskId}:export` | 导出轨迹/评分/报告 |

### 8.1 ★ 批量虚拟筛选

**POST** `/api/v1/screen/virtual-screening`

```json
{
  "projectId": "prj_...",
  "setId": "cset_...",
  "structureId": "str_...",
  "pocketId": "pkt_...",
  "stages": [
    { "stage": "CONFORMER", "enabled": true, "params": { "maxConfs": 8 } },
    { "stage": "PHARMACOPHORE", "enabled": true, "params": { "minHit": 3 } },
    { "stage": "DOCKING", "enabled": true, "params": { "exhaustiveness": 8, "topPoses": 3, "seed": 42 } },
    { "stage": "RESCORE", "enabled": true, "params": { "model": "rescoring-rf", "version": "1.0" } }
  ],
  "thresholds": { "dockingScoreMax": -8.0 },
  "shardSize": 500,
  "priority": "BULK"
}
```

响应：`{ "taskId": "tsk_...", "shardCount": 20, "status": "QUEUED", "estimatedWaitSeconds": 600 }`

结果：

```json
{
  "summary": { "input": 10000, "passedConformer": 9850, "passedPharmacophore": 4210,
               "passedDocking": 860, "finalRanked": 860 },
  "items": [
    { "rank": 1, "candidateId": "cand_...", "finalScore": -11.24,
      "docking": { "score": -10.8, "poseUrn": "..." },
      "rescore": { "score": -11.24 } }
  ]
}
```

### 8.2 MD 计算

**POST** `/api/v1/md/simulate`

```json
{
  "projectId": "prj_...",
  "complexUrn": "oss://drp-results/.../complex.pdb",
  "params": {
    "forceField": "amber99sb-ildn",
    "waterModel": "tip3p",
    "durationNs": 100,
    "timestepFs": 2,
    "temperatureK": 300,
    "pressureBar": 1
  },
  "resourceProfile": { "dcu": 2, "cpu": 16, "memGB": 64, "expectedMinutes": 2880 },
  "checkpointIntervalMinutes": 60
}
```

---

## 9. 工作流与任务（M6）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v1/workflow-templates` | 工作流模板列表（预置 + 项目自定义） |
| GET | `/api/v1/workflow-templates/{id}` | 模板详情（DAG 定义 + 默认参数） |
| POST | `/api/v1/projects/{id}/workflow-templates` | 保存自定义模板 |
| POST | `/api/v1/workflows:run` | 启动工作流实例 |
| GET | `/api/v1/projects/{id}/workflows` | 工作流实例列表 |
| GET | `/api/v1/workflows/{id}` | 实例详情（节点状态） |
| GET | `/api/v1/workflows/{id}/nodes` | 节点列表（含依赖与对应 taskId） |
| POST | `/api/v1/workflows/{id}:cancel` | 取消工作流 |
| POST | `/api/v1/workflows/{id}:retry` | 从失败节点重试 |
| GET | `/api/v1/tasks` | 任务列表（项目/类型/状态/提交人筛选） |
| GET | `/api/v1/tasks/{id}` | 任务详情（状态、进度、阶段、资源、追溯元数据） |
| GET | `/api/v1/tasks/{id}/events` | SSE 实时状态与进度 |
| GET | `/api/v1/tasks/{id}/logs` | 任务日志（分页，支持 level/stage/时间过滤） |
| POST | `/api/v1/tasks/{id}:cancel` | 取消任务 |
| POST | `/api/v1/tasks/{id}:retry` | 重新提交（可覆盖参数） |
| GET | `/api/v1/tasks/{id}/artifacts` | 产物列表 |
| GET | `/api/v1/artifacts/{id}/download` | 下载产物（302 到预签名 URL） |
| GET | `/api/v1/compute/queue` | 队列概览（排队数、各项目占用、DCU 使用率） |
| GET | `/api/v1/compute/quota` | 当前项目配额与已用（**v1.1**：返回 `usedDcuMinutes` / `usedCpuMinutes` / `usedTotalMinutes` / `limitMinutes` / `period` / `overdraftRatio` / `exceeded`） |

### 9.1 启动工作流

**POST** `/api/v1/workflows:run`

```json
{
  "projectId": "prj_...",
  "templateCode": "wf-target-to-candidate",
  "params": {
    "targetId": "tar_...",
    "pocketId": "pkt_...",
    "generation": { "model": "std-diff", "numMolecules": 200 },
    "admet": { "enabled": true },
    "docking": { "enabled": true, "exhaustiveness": 8 }
  },
  "onNodeFailure": "ABORT"
}
```

响应：`{ "workflowId": "wfi_...", "status": "RUNNING", "nodes": [...] }`

### 9.2 任务详情（追溯视图）

**GET** `/api/v1/tasks/{id}`

```json
{
  "id": "tsk_...",
  "taskType": "DOCKING",
  "status": "RUNNING",
  "progress": 62,
  "stage": "docking_shard_7/20",
  "priority": "BULK",
  "scale": { "kind": "L", "itemCount": 2000, "pool": "BATCH" },
  "submittedBy": "zhangwei",
  "timeline": { "created": "...", "started": "...", "finished": null },
  "resourceProfile": { "dcu": 0, "cpu": 16, "memGB": 32, "expectedMinutes": 45, "cost": { "dcuMinutes": 0, "cpuMinutes": 720, "totalMinutes": 11.25 } },
  "tool": { "name": "vina", "version": "1.2.5" },
  "model": null,
  "imageRef": "harbor/drp/vina:1.2.5-py3.10",
  "params": { "exhaustiveness": 8, "seed": 42 },
  "inputs": [ { "role": "RECEPTOR", "urn": "oss://...", "sha256": "...", "version": 2 } ],
  "outputs": [ { "type": "SCORE", "urn": "oss://...", "sha256": "..." } ],
  "bizRef": { "projectId": "prj_...", "targetId": "tar_...", "setId": "cset_..." }
}
```

---

## 10. 结果与追溯（M7）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v1/projects/{id}/results` | 项目结果列表（按任务/候选物维度） |
| GET | `/api/v1/candidates/{id}/results` | 候选物相关全部结果 |
| GET | `/api/v1/results/{taskId}` | 结果详情（指标 + 产物 + 3D 可视化引用） |
| GET | `/api/v1/results/{taskId}/traceability` | 追溯包 JSON（输入/环境/参数/产物） |
| POST | `/api/v1/results/{taskId}:export` | 导出结果文件与报告 |
| POST | `/api/v1/results:compare` | 多任务结果比较（`{"taskIds":[...]}`） |
| GET | `/api/v1/results/{taskId}/report` | 分析报告（PDF/HTML URN） |
| GET | `/api/v1/structures/{id}/viewer` | 三维可视化数据（结构 + 口袋 + 配体，供 Mol* 渲染） |

### 10.1 追溯包

**GET** `/api/v1/results/{taskId}/traceability`

```json
{
  "taskId": "tsk_...",
  "taskType": "DOCKING",
  "submittedBy": "zhangwei",
  "timeline": { "created": "...", "started": "...", "finished": "..." },
  "inputs": [ { "urn": "...", "sha256": "...", "dataVersion": 2 } ],
  "environment": {
    "image": "harbor/drp/vina:1.2.5-py3.10",
    "tool": { "name": "vina", "version": "1.2.5" },
    "model": null
  },
  "params": { "exhaustiveness": 8, "seed": 42 },
  "outputs": [ { "urn": "...", "sha256": "...", "sizeBytes": 1048576 } ],
  "logs": "oss://drp-logs/20260701/tsk_.../part-1.log"
}
```

---

## 11. 管理与运维接口

| 方法 | 路径 | 说明 |
|---|---|---|
| GET/POST/PUT | `/api/v1/admin/models` | 模型注册与启停 |
| GET/POST/PUT | `/api/v1/admin/tools` | 工具注册与启停 |
| GET | `/api/v1/admin/compute/nodes` | 算力节点状态（CPU/DCU 使用率） |
| GET | `/api/v1/admin/compute/queue` | 全局队列 |
| POST | `/api/v1/admin/compute/drain` | 节点排水（维护前） |
| GET | `/api/v1/admin/audit-logs` | 审计日志查询 |
| POST | `/api/v1/admin/backup:trigger` | 手动触发备份 |

---

## 12. 接口设计纪律

1. **列表接口强制分页**，禁止无界返回；大字段（序列、SMILES 列表）只在详情接口返回。
2. **所有写接口校验项目权限**，且 `projectId` 必须来自服务端会话上下文校验，不可仅依赖请求体。
3. **任务提交接口必须幂等**，重复 `X-Idempotency-Key` 返回首次结果，不重复扣配额。**幂等键的存储与判定规则见 `04` §5.5**：键按 `(scope, key)` 唯一，`scope = {user}:{METHOD}:{path}`；同键同体重放首次响应，同键异体返回 `40905`，键尚在处理中返回 `40904`（`Retry-After: 2`），键保留 **24 小时**。
4. **写接口的并发冲突统一按 `04` §5.6 处理**：乐观锁冲突返回 `40903` 并带 `currentVersion`；唯一约束冲突返回 `40901` 并在 `detail` 指明冲突字段；**行锁等待超时返回 `50302`**（不是 `42902`——`42902` 是「并发任务超限」的业务限流码，两者语义不可混用，见 `04` §5.6 修订说明）。
5. **结果类接口支持维度筛选**，与 PRD 中筛选/排序需求一一对应。
6. **文件相关接口一律返回预签名 URL**，服务端不下发文件内容（大文件场景）。
7. **错误提示需可执行**：返回给用户的是「格式不支持，仅支持 .sdf/.smi/.csv」而非「参数错误」。
8. **接口变更需同步更新本文件**，并纳入版本管理（URL 版本号 `/v1` 破坏性变更时升级）。
