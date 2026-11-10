# 协作规范

本仓库是中国医药一期交付的团队开发仓库。这份文档只回答一个问题：**多人同时改，怎么不互相踩、不把交付搞崩**。

需求与设计口径以 `docs/` 为准，本文只管协作流程。

---

## 1. 分支模型

### 1.1 分支一览

| 分支 | 生命周期 | 从哪切 | 合到哪 | 说明 |
|---|---|---|---|---|
| `main` | 长期 | — | — | **交付主干**。任何时点都应能构建出可交付版本。受保护，只能经 PR 合入。 |
| `feature/<模块>-<主题>` | ≤ 5 工作日 | `main` | `main` | 新功能 |
| `fix/<模块>-<主题>` | ≤ 2 工作日 | `main` | `main` | 缺陷修复 |
| `refactor/<模块>-<主题>` | ≤ 5 工作日 | `main` | `main` | 不改行为的重构（如 `agents/aidd` 拆包） |
| `docs/<主题>` | ≤ 2 工作日 | `main` | `main` | 纯文档 |
| `release/v1.x.y` | 交付周期 | `main` | `main` + tag | 交付候选，只收回归修复，不收新功能 |
| `spike/<主题>` | ≤ 3 工作日 | `main` | **不合** | 技术验证，验证完写结论并删除 |

**为什么主干是 `main` 而不是 `develop`**：中国医药文档 `docs/11` 的 GitLab 流水线按 `main` 为主干设计（`feat/fix ──MR──▶ main`），交付线要能直接对应这份验收文档。产品线的 `develop/beta` 双长期分支模型不适用于 3 个月的交付节奏——多一层集成分支只会让回滚更麻烦。

### 1.2 命名示例

```bash
git switch -c feature/target-entity-crud
git switch -c refactor/aidd-unbundle     # 拆 agents/aidd
git switch -c fix/task-cancel-race
git switch -c docs/api-traceability
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

PR 标题同提交规范。一个 PR 只做一件事：改了 30 个文件、跨 5 个模块的 PR 会被打回要求拆分。

### 2.5 合并

- CI 全绿 + 至少 1 人 approve → **squash merge**（保持 `main` 线性，`git log` 可读）；
- 合并后删远端分支；
- `main` 上出现回归，**revert 那个 squash 提交**，不要在其上打补丁。

---

## 3. 代码归属（CODEOWNERS）

见 `.github/CODEOWNERS`。规则：**谁写的模块谁 review**。

| 路径 | 归属 |
|---|---|
| `backend/app/api/`、`backend/app/services/` | 后端 |
| `backend/app/models/`、`backend/alembic/` | 后端（**改表必须双人确认**，见 4.1） |
| `backend/app/execution/`、`backend/app/tasks/` | 平台/调度 |
| `frontend/src/views/`、`frontend/src/components/` | 前端 |
| `deploy/`、`.github/` | 运维/发布经理 |
| `docs/0*`~`docs/1*` | 产品经理 |

团队尚未扩充时，CODEOWNERS 全部指向仓库管理员；成员到位后逐条改。

---

## 4. 高危改动清单

以下改动**必须在 PR 描述里单列风险与回滚方式**，并由第二人确认：

### 4.1 数据库迁移

- 新增迁移文件后才能改模型，不允许只改 ORM 不写迁移；
- 迁移必须**可回滚**（写 `downgrade()`），且不得删除已有列——先标记废弃，下个版本再删；
- 已合入 `main` 的迁移文件**不得修改**，有错就新增一条修正迁移。

### 4.2 任务状态机与执行器

改 `backend/app/tasks/state_machine.py` 或 `backend/app/execution/` 会影响所有在跑任务。要求：
- 补状态转换的单测（现有测试在 `test/test_task_state*.py`）；
- 说明对**已在运行中的任务**的影响。

### 4.3 删除代码

拆包/删除前先在 Issue 里列出所有引用点（`grep -rn "from app.<模块>" backend/`），确认无遗漏。参考已完成的 `agents/aidd` 拆包（步骤 3）：它混装了三种东西——真 Agent（planner/graph/llm，已删）、工具能力注册表（`tools/capability_registry.py`，工作流成功回调依赖）、内建工具执行（`tools/builtin_tools.py`，Vina 对接依赖），所以**只能拆包不能整目录删**。教训与对照表见 [docs/internal/17](docs/internal/17-交付仓库与分支策略.md) 第 5 节。

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

任何卡住进度的事项，**当天**开 `blocker` Issue 并登记到 `docs/03B-待决策与阻塞项总表.md`。不要只在聊天里说——聊天记录不会进验收材料。

---

## 7. 发布

```bash
# 1. 从 main 切发布分支
git switch -c release/v1.0.0 main

# 2. 只收回归修复，每笔都要 cherry-pick 回 main
git cherry-pick -x <commit>

# 3. 全量回归
python -m pytest test/ -v
cd frontend && npm run test && npm run test:e2e

# 4. 打 tag（受保护，见仓库 rulesets）
git tag -a v1.0.0 -m "中国医药一期交付 v1.0.0"
git push origin v1.0.0

# 5. 构建离线交付包
bash scripts/build-offline-package.sh --version v1.0.0
```

版本号语义：`v<major>.<minor>.<patch>`；交付候选加 `-rc.N`，甲方验收通过后转正式版。

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
