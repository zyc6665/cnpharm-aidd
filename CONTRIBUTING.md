# 协作规范

本仓库是中国医药一期交付的团队开发仓库。这份文档只回答一个问题：**多人同时改，怎么不互相踩、不把交付搞崩**。

需求与设计口径以 `docs/` 为准，本文只管协作流程。

---

## 1. 分支模型

### 1.1 分支一览

| 分支 | 生命周期 | 从哪切 | 合到哪 | 说明 |
|---|---|---|---|---|
| `main` | 长期 | — | — | **交付主干**。任何时点都应能构建出可交付版本。受保护，只能经 PR 合入。 |
| `feature/<role>-<issue号>-<简述>` | ≤ 5 工作日 | `main` | `main` | 新功能 |
| `fix/<role>-<issue号>-<简述>` | ≤ 2 工作日 | `main` | `main` | 缺陷修复 |
| `refactor/<role>-<issue号>-<简述>` | ≤ 5 工作日 | `main` | `main` | 不改行为的重构（如服务拆包） |
| `docs/<role>-<issue号>-<简述>` | ≤ 2 工作日 | `main` | `main` | 纯文档 |
| `release/standard-v1.0`、`release/full-v2.0` | 交付周期 | `main` | tag（不回 main） | 标准版 / 完整版一次性交付分支，只收回归修复；现场 bugfix 需 cherry-pick 回 `main` |
| `spike/<主题>` | ≤ 3 工作日 | `main` | **不合** | 技术验证，验证完写结论并删除 |

**为什么主干是 `main` 而不是 `develop`**：中国医药文档 `docs/11` 的 GitLab 流水线按 `main` 为主干设计（`feat/fix ──MR──▶ main`），交付线要能直接对应这份验收文档。产品线的 `develop/beta` 双长期分支模型不适用于 3 个月的交付节奏——多一层集成分支只会让回滚更麻烦。

### 1.2 「标准版 → 完整版」一次性交付

本仓库发版模式是**标准版 → 完整版**私有化离线一次性交付，分支模型如下：

- **单主干 `main`**：功能先合 `main`；完整版未就绪的能力用 **Feature Flag** 包起来（默认关），保证 `main` 任何时点都能出「标准版」。
- **两个短命发版分支**：`release/standard-v1.0`（标准版）、`release/full-v2.0`（完整版），只用于冻结交付，**只收回归修复、不收新功能**。
- **现场 bugfix 回主干**：在发版分支修好后 **`cherry-pick -x` 回 `main`**，避免修复丢失。
- **产品线 `upstream`（`CPUmodel_V2`）**：**仅 `@zyc6665` 拥有 cherry-pick 权限**，其他人不要操作 `upstream`。

### 1.3 新人只配置 `origin`

新克隆仓库**只配置 `origin`**（团队主仓），不要自行添加 `upstream` 或其它远端。需要与产品线同步时找 P1，由 P1 统一执行 cherry-pick。

### 1.4 命名示例

分支命名统一 `{type}/{role}-{issue号}-{简述}`（`type` ∈ feature/fix/refactor/docs/chore，`role` ∈ fe/be/ops/arch）。

```bash
git switch -c feature/be-123-target-entity-crud
git switch -c refactor/be-45-task-service-split
git switch -c fix/be-88-task-cancel-race
git switch -c docs/arch-56-api-traceability
```

模块名用后端目录或前端页面名：`target` `pocket` `candidate` `task` `workflow` `artifact` `scheduler` `dcu`。**不要**用 `feature/zhangsan-dev`、`feature/test`、`feature/new` 这类无信息量命名。

---

## 2. 日常开发流程

### 2.1 开工前

```bash
# 1. 同步主干
git switch main && git pull --ff-only

# 2. 从 Issue 领任务，确认验收标准写在 Issue 里
#    没有 Issue 就先开一个——事后补 Issue 等于没写

# 3. 切分支
git switch -c feature/pocket-selection
```

**为什么要先有 Issue**：交付期要能回答「这行代码对应哪条需求」。Issue 是需求编号（`M2-FR-06`）落到具体改动的唯一衔接点。

### 2.2 开发中

```bash
# 小步提交，一次提交只做一件事
git add -p                      # 逐块暂存，避免把无关改动混进来
git commit -m "feat(pocket): add pocket selection persistence

口袋可标记为选定并持久化，供分子生成任务复用。

Refs: M2-FR-06"

# 定期变基主干，避免最后一次性解冲突
git fetch origin
git rebase origin/main
```

**提交信息格式**（与产品线一致，便于统一工具链）：

```
<type>(<scope>): <subject>

<body：为什么这么改，不是改了什么——改了什么看 diff>

Refs: <需求编号 / 决策编号 / Issue 号>
```

`type`：`feat` `fix` `refactor` `docs` `test` `chore` `perf` `ci`
`scope`：模块名，见 1.2

### 2.3 提交前自检（本地跑，不要等 CI）

```bash
# 后端
python -m flake8 backend/app --select F401
python -m pytest test/ -v

# 前端
cd frontend
npm run test
npm run build

# 改了执行器 / 卡位 / 模型相关，额外跑
npm run test:e2e -- --project=chromium --reporter=list --workers=1
```

CI 与本清单一一对应。**本地过了 CI 才有可能过**——CI 只做二次确认，不当第一道防线。

### 2.4 提 PR

```bash
git push -u origin feature/pocket-selection
gh pr create --fill --base main
```

PR 必须填完模板的「影响模块」和「测试结果」。**未运行项要写原因**，写「后端测试未跑：只改前端样式」比留空更被接受。

PR 标题同提交规范。一个 PR 只做一件事：改了 30 个文件、跨 5 个模块的 PR 会被打回要求拆分。**单 PR 原则上 ≤ 800 行（不含测试与自动生成文件）**，超过要拆。

### 2.5 合并

- CI 全绿 + 至少 1 人 approve → **squash merge**（保持 `main` 线性，`git log` 可读）；
- 合并后删远端分支；
- `main` 上出现回归，**revert 那个 squash 提交**，不要在其上打补丁。

---

## 3. 代码归属（CODEOWNERS）

见 `.github/CODEOWNERS`。规则：**谁写的模块谁 review**。

| 路径 | 归属 |
|---|---|
| `/frontend/` | P3 `@PLACEHOLDER_FE`（前端独占） |
| `/backend/app/api/v1/`、`/backend/app/services/` | P2 `@PLACEHOLDER_BE2` + P1 `@zyc6665` 复核 |
| `/backend/app/models/`、`/backend/alembic/`、`/backend/app/config.py`、`/backend/app/api/v1/__init__.py`、`platform_tool_seeding.py` | P1 `@zyc6665`（契约 / 高危，**改表必须双人确认**，见 4.1） |
| `/backend/app/{tasks,execution,worker}/` | P1 `@zyc6665`（L1 调度） |
| `/deploy/`、`/scripts/build-offline-package.sh`、`/backend/app/tool_templates/`、`/example/` | P4 `@PLACEHOLDER_OPS_MODEL` + P1 复核 |
| `/.github/` | P1 `@zyc6665` |

> `@PLACEHOLDER_BE2` / `@PLACEHOLDER_FE` / `@PLACEHOLDER_OPS_MODEL` 是占位符，**启用 Code Owners 强制审批前必须替换为真实 GitHub 账号**（见 `.github/CODEOWNERS` 顶部说明）。

---

## 4. 高危改动清单

以下改动**必须在 PR 描述里单列风险与回滚方式**，并由第二人确认：

### 4.1 数据库迁移

- 新增迁移文件后才能改模型，不允许只改 ORM 不写迁移；
- 迁移必须**可回滚**（写 `downgrade()`），且不得删除已有列——先标记废弃，下个版本再删；
- 已合入 `main` 的迁移文件**不得修改**，有错就新增一条修正迁移；
- **必须保持单头**：`python -m alembic heads` 只能输出 1 行。出现多个 head 说明迁移链分叉，先 `git rebase origin/main` 合并 head 再提 PR（CI 的「迁移链」作业已强制该检查）。

### 4.2 任务状态机与执行器

改 `backend/app/tasks/state_machine.py` 或 `backend/app/execution/` 会影响所有在跑任务。要求：
- 补状态转换的单测（现有测试在 `test/test_task_state*.py`）；
- 说明对**已在运行中的任务**的影响。

### 4.3 删除代码

拆包/删除前先在 Issue 里列出所有引用点（`grep -rn "from app.<模块>" backend/`），确认无遗漏。参考已完成的 `agents/aidd` 拆包（步骤 3）：它混装了三种东西——真 Agent（planner/graph/llm，已删）、工具能力注册表（`tools/capability_registry.py`，工作流成功回调依赖）、内建工具执行（`tools/builtin_tools.py`，Vina 对接依赖），所以**只能拆包不能整目录删**。教训与对照表见 [docs/17](docs/internal/17-交付仓库与分支策略.md) 第 5 节。

### 4.4 离线合规

**任何引入公网域名、外部 API、遥测上报的代码都不合入**。CI 的 `offline-check` 作业会扫描常见域名（pubchem、rcsb、ebi.ac.uk、pdbbind、googleapis 等）。确需例外（如内网镜像源）在 `.github/offline-allowlist.txt` 登记并说明理由。

---

## 5. 冲突预防

| 冲突源 | 预防手段 |
|---|---|
| 多人改同一文件 | 按模块切分支；`models/` 与 `alembic/` 由后端指定一人当「迁移串行口」，其他人排期 |
| 迁移文件序号撞车 | 迁移文件名用 `日期_序号_主题`，取号前先在群里报一声 |
| 前端路由/菜单同时改 | `frontend/src/router/` 的改动集中在 PR 末尾做，避免所有分支都碰 |
| 依赖版本同时升级 | 依赖升级单独开 `chore/deps-*` PR，不与功能混提 |
| 文档与代码不同步 | 涉及接口/表结构变更，PR 内必须同时改对应 `docs/05`/`docs/04` |

**长时间不合并的分支就是技术债**。超过 5 个工作日还没提 PR，说明任务该拆了。

---

## 6. Issue 规范

### 6.1 类型

新建 Issue 时选择对应模板即可自动打上标签（模板在 `.github/ISSUE_TEMPLATE/`）：

| 标签 | 用途 | 模板 |
|---|---|---|
| `feature` | 功能开发 | `feature.md` |
| `bug` | 缺陷 | `bug.md` |
| `blocker` | **阻塞交付**，需每日同步 | `blocker.md` |
| `change` | 需求变更（走变更控制） | `change.md` |
| `refactor` | 重构 | 无模板，直接建 |
| `docs` | 文档 | 无模板，直接建 |
| `decision` | 待甲方/PM 决策，同步登记到 `docs/03B` | 用 `blocker.md` |

> 仓库已关闭「空白 Issue」入口 —— 强制走模板，避免出现「就一句话、没有需求来源」的 Issue。

### 6.2 必须包含

- **需求来源**：`M2-FR-06` / `D-25` / `docs/03 §5.2`；
- **验收标准**：怎样算做完，可测；
- **影响面**：涉及哪些模块/表/接口。

### 6.3 阻塞项

任何卡住进度的事项，**当天**开 `blocker` Issue 并登记到 `docs/01-需求/03B-待决策与阻塞项总表.md`。不要只在聊天里说——聊天记录不会进验收材料。

---

## 7. 发布

一次性离线交付分「标准版」与「完整版」两个节点，均从 `main` 切短命发版分支冻结：

```bash
# 1. 从 main 切发版分支（标准版 / 完整版各一条）
git switch -c release/standard-v1.0 main     # 或 release/full-v2.0 main

# 2. 完整版未就绪能力靠 Feature Flag 关闭保证标准版可交付；
#    发版分支只收回归修复，每笔修完都要 cherry-pick 回 main
git cherry-pick -x <commit>

# 3. 全量回归
python -m pytest test/ -v
cd frontend && npm run test && npm run test:e2e

# 4. 打 tag（受保护，见仓库 rulesets）
git tag -a v1.0.0 -m "中国医药交付 标准版 v1.0.0"
git push origin v1.0.0

# 5. 构建离线交付包（P4 主责）
bash scripts/build-offline-package.sh --version v1.0.0
```

- **产品线 `upstream` 同步**：仅 `@zyc6665`（P1）可对 `upstream`（`CPUmodel_V2`）执行 cherry-pick；其他人只配 `origin`。
- 版本号语义：`v<major>.<minor>.<patch>`；交付候选加 `-rc.N`，甲方验收通过后转正式版。

---

## 8. 禁止事项

- ❌ `git push --force` 到 `main` / `release/*`（受保护分支会直接拒绝）
- ❌ 直接 commit 到 `main`
- ❌ 提交密钥、token、真实密码、甲方数据
- ❌ 提交 `node_modules/`、`.venv/`、`*.db`、模型权重文件
- ❌ 修改已合入的 alembic 迁移
- ❌ 在 PR 里混入无关格式化改动（会让 review 失效）
- ❌ 用「临时绕过」的方式让 CI 变绿（改测试断言、注释掉检查）

---

## 9. 遇到问题

| 情况 | 做法 |
|---|---|
| CI 挂了但本地是好的 | 先看是不是 `core.autocrlf` 换行问题：`git config core.autocrlf` 应为 `true`，仓库 `.gitattributes` 已统一入库为 LF |
| 不知道某段代码能不能删 | 先 `grep -rn` 找引用，再在 Issue 里列清单，别直接删 |
| 需求文档之间打架 | 以 `docs/03B` 的决策状态为准；未关闭的按最保守方案实现并开 `decision` Issue |
| 需要甲方确认才能继续 | 开 `decision` Issue + 登记 `docs/03B`，同时做不受影响的部分 |

---

## 10. 新人 Day 1 Onboarding 极速清单

目标：**当天**把环境跑通、跑绿基线、提出第一个 10 行小 PR。

- [ ] **克隆** `cnpharm-aidd`（只配 `origin`）：`git clone <repo-url> && cd cnpharm-aidd`
- [ ] **配 `.env`**：按 `deploy/compose/README.md` 从 `.env.example` 复制 `backend/.env`；本机开发连接串指向 `127.0.0.1`（联调才指 `10.202.2.228`），见 `AGENTS.md` §4
- [ ] **起本机数据栈**：`docker compose -f deploy/compose/docker-compose.dev.yml up -d`
- [ ] **跑通后端**：`cd backend && python -m venv .venv && . .venv/Scripts/activate && pip install -r requirements-dev.txt` → `uvicorn app.main:app --reload`；`curl 127.0.0.1:8000/api/v1/system/health` 全绿
- [ ] **跑通 worker / beat**：`celery -A app.worker.celery_app worker --pool=threads -Q high_priority,gpu_queue,heavy_compute,cpu_queue,default,tool_tasks,maintenance,monitoring` + `celery -A app.worker.celery_app beat`
- [ ] **跑通前端**：`cd frontend && npm ci && npm run dev`（Node 用 `.nvmrc` 的 20）
- [ ] **跑绿基线**：`python -m flake8 backend/app --select F401`、`python -m pytest test/ -v`、`cd frontend && npm run test && npm run build`
- [ ] **提首个 10 行测试 PR**：认领一个 `Ready` 小 Issue，写一个小测试 / 小修，走完「切分支 → 小步提交 → PR → 1 人评审 → squash 合并」

> 卡住先看 `AGENTS.md` 第 7 节「已知的坑」，仍不通就在 Issue 里开 `blocker`。
