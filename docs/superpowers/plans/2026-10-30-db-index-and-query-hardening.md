# 数据库索引预留与查询规范硬化（2026-10-30）

## Goal

在不改业务语义的前提下，把「现在能跑、数据量上来会慢」的查询路径提前堵住：

1. 补齐**复合索引**（等值列在前、排序列在后），让列表/结果/审计/日志这类高频分页查询不再 `USE TEMP B-TREE FOR ORDER BY`。
2. 清掉**前缀冗余索引**，尤其是写多读少的 `audit_logs`（现 10 个索引 / 13 列），减少每次插入的索引维护。
3. 修掉**模型声明与迁移不一致**的四处（生产预存库会缺索引或约束）。
4. 把「查询规范」写成可执行的硬规则，并对三处最贵的写法做等价改写。

## Architecture

分三层，互不耦合：

- **索引层**（`backend/app/models/*.py` 的 `Index(...)` + 一个新迁移）：只加/删索引与约束，不改任何 SQL 语义。生产走 `CONCURRENTLY`，SQLite 走普通建索引（方言分支）。
- **查询层**（`backend/app/services/*.py`、`backend/app/api/v1/*.py`）：把「索引用不上」的写法改成「索引用得上」，结果集与返回结构不变。
- **规范层**（`docs/20-数据库索引与查询规范.md`）：把判断依据写成团队可执行的条目，避免下一个人再引入同类写法。

## Tech Stack

SQLAlchemy 2.0 async / Alembic / PostgreSQL 16（生产）/ SQLite（开发与测试）。

## 实测基线（本机 SQLite，30,000 tasks / 120,000 audit_logs）

| 查询 | 现状 | 加复合索引后 | 计划变化 |
|---|---|---|---|
| 结果中心：`project + 终态 + finished_at DESC` | 6.26 ms | 1.10 ms | `SEARCH ix_tasks_project_id` + **TEMP B-TREE** → 走复合索引 |
| 任务列表：`user + status + created_at DESC` | 3.83 ms | 1.03 ms | 同上 |
| 审计：`action + 时间范围 + created_at DESC` | **51.07 ms** | **0.69 ms** | 全表按 action 过滤后排序 → 直接走 `(action, created_at)` |
| 审计计数：时间范围 `count(*)` | 18.87 ms | 8.50 ms | 已走 covering index（无需再优化） |

> 表越大差距越大：`USE TEMP B-TREE FOR ORDER BY` 是把整个过滤结果集排序，代价随命中行数增长；
> 复合索引把「过滤 + 排序 + LIMIT」压成一次索引区间扫描。

## Spec

### 一、索引层（本 PR 实施）

**新增（现在就该有）**

| 表 | 索引 | 支撑查询 |
|---|---|---|
| `tasks` | `(project_id, status, created_at)` | `task_views.py` 项目任务列表、结果中心 |
| `tasks` | `(user_id, status, created_at)` | `task_views.py` 我的任务 |
| `tasks` | `(project_id, status, finished_at DESC, created_at DESC)` | `results.py:209` 结果中心排序 |
| `tasks` | `(updated_at) WHERE status = 'QUEUED'`（partial） | `queue_timeout.py` 排队超时巡检 |
| `tasks` | `(status, finished_at)` | `project_quotas.py` 配额核销扫描 |
| `task_logs` | `(task_id, timestamp)` | 任务日志增量拉取、`task_event_stream.py` |
| `artifacts` | `(project_id, artifact_type, updated_at)` | 资产列表 |
| `artifact_versions` | `(artifact_id, sha256, status)` | 产物去重写入判据 |
| `candidates` | `(project_id, created_at)` | 候选物列表（无类型过滤时） |
| `candidate_sets` | `(project_id, created_at)` | 候选集列表 |
| `files` | `(owner_id, created_at)` | 我的文件列表 |
| `workflow_runs` | `(created_at) WHERE status NOT IN (终态)`（partial） | 工作流对账巡检 |
| `tools` | `(status, created_at)` | 公开工具列表（`tools.status` 现在无索引） |

**删除（被更长前缀索引覆盖，纯维护成本）**

`project_members.project_id`、`task_input_snapshots.task_id` 与 `(task_id, input_role)`、`artifact_versions.artifact_id`、`artifact_version_files.artifact_version_id`、`pockets.structure_id`、`pocket_residues.pocket_id`、`candidates.project_id`、`audit_logs.actor`、`audit_logs.resource_type`、`audit_logs.result`（4 个值，低基数）、`audit_logs.actor_id`、`audit_logs.resource_id`。

> `audit_logs` 从 10 个索引降到 6 个：`actor_created`、`resource`、`action`、`request_id`、`created_at`，加新增的 `(action, created_at)`。

**模型 / 迁移一致性修正**

- `datasets` 补 `uq_datasets_project_name_type`（模型有、迁移从未建，预存库去重只靠应用层）。
- `compounds.inchikey` 收敛为**一个**唯一索引（迁移里出现过「唯一约束 + 非唯一索引同名」双份）。
- `ix_candidates_attrs_gin` 补进模型（迁移有、模型无 → fresh 库缺 GIN）。
- 删 `ix_upload_sessions_idempotency_key`（模型无、迁移独有，且已被 `uq_upload_sessions_project_idem` 覆盖）。

### 二、查询层（本 PR 实施的三处等价改写）

1. `backend/app/api/v1/results.py:209`：`ORDER BY finished_at DESC NULLS LAST` 与索引方向冲突
   （ASC 索引反扫得到 `NULLS FIRST`）。改为 `finished_at IS NOT NULL` 条件下按 `finished_at DESC` 排序，
   语义等价（终态任务必有 finished_at；历史脏数据单独兜底到末尾）。
2. `backend/app/services/task_views.py:262-269`：8 列 `ilike('%kw%')` + 两表 outer join。
   改为「`name` 走前缀/子串 LIKE + `id` 精确匹配」优先，`error_message`/`progress_message`
   这类长文本移出关键字搜索（它们由日志检索承担）；保留 join 但不再参与 OR 展开。
3. `backend/app/execution/records.py:278-281`：`outerjoin(Task, Task.id == request_snapshot["task_id"].as_string())`
   JSON 提取进 JOIN 条件。加真列 `execution_records.task_id`（回填自 `request_snapshot`），
   改按真列 join，并加索引。

### 三、规范层

`docs/20-数据库索引与查询规范.md`：列顺序规则、什么时候不加索引、禁止清单（前导 `%` LIKE、函数包列、
JSON 提取进 WHERE/JOIN、无界 `offset`）、分页与计数写法、新表上线检查表。

## Global Constraints

- 只加/删索引与约束，**不改任何返回值结构**；所有既有测试必须继续通过。
- 迁移必须在 **SQLite 与 PostgreSQL** 双向可跑（`upgrade head` / `downgrade`）。
- 生产路径用 `CREATE INDEX CONCURRENTLY`（需在 autocommit 块里），SQLite 用普通 `CREATE INDEX`。
- 新增索引必须写清「支撑哪条查询」，没有对应查询的不加。
- 不引入 `pg_trgm`、不引入分区、不改主键、不动 `molecule_fingerprints` 的检索方式。

## Review Focus

1. 复合索引的**列顺序**是否真能覆盖 `WHERE ... ORDER BY ... LIMIT`（要看 EXPLAIN，不是看列名）。
2. 删除的索引是否真的被更长前缀覆盖（唯一约束与普通索引不可混为一谈）。
3. `tasks` 上索引已有 7 个，新增 3 个后是否过度（这是全库写最频繁的表之一）。
4. 三处查询改写是否严格等价（尤其 `NULLS LAST` → `IS NOT NULL`）。
5. 迁移的 `down` 是否能真正回到原状，而不是「建回来但语义不同」。
