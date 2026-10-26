/**
 * 研发决策记录与项目阶段的类型（docs/03 §3.6.2、docs/05 §3.2/§3.3、docs/04 §9.5）。
 *
 * 字段名与后端 `serialize_decision` / `_stage_payload` 的原样输出保持一致：
 * 决策对象是 snake_case，阶段对象是 camelCase（见
 * `backend/app/api/v1/decisions.py` 的模块注释）。这里不做改名，
 * 免得每个调用点都要在两套命名之间翻译。
 */

/** 决策点（docs/03 §3.6.2）：DP1 靶点是否值得推进 → DP5 最终推荐进入实验。 */
export type DecisionPoint = 'DP1' | 'DP2' | 'DP3' | 'DP4' | 'DP5'

/** 决策对象类型；`CANDIDATE_SET` 额外校验成员快照归属。 */
export type DecisionSubjectType = 'TARGET' | 'POCKET' | 'CANDIDATE_SET' | 'STRUCTURE'

/** 决策结论。 */
export type DecisionVerdict = 'SELECTED' | 'EXCLUDED'

/** 快照里「当时没录到分」的标记（`app.models.decisions.SCORE_SOURCE_MISSING`）。 */
export const SCORE_SOURCE_MISSING = 'missing'

/** `decision_items.snapshot_attrs` 里可能出现的键；其余键是调用方自定义的属性。 */
export interface DecisionSnapshotAttrs {
  score_source?: string
  [key: string]: unknown
}

/**
 * 成员快照的一行（`serialize_decision` 的 `items[]`）。
 *
 * `snapshot_score` 为 `null` 且 `snapshot_attrs.score_source === 'missing'` 时表示
 * 「当时没录分」——只追加表里它和「当时为 0」一旦混淆就再也分不开，所以 UI 必须
 * 显示「未记录」而不是 `0` 或 `-`。
 */
export interface DecisionItem {
  candidate_id: string
  verdict: DecisionVerdict
  snapshot_score: number | null
  snapshot_rank: number | null
  snapshot_attrs: DecisionSnapshotAttrs
}

/**
 * 一条决策记录（`serialize_decision`）。
 *
 * `items` 是权威的成员快照，`selected_ids`/`excluded_ids` 由后端从它派生；
 * 页面读 `items` 渲染明细，读派生的两个字段做计数，两者不会打架。
 */
export interface DecisionRecord {
  id: string
  project_id: string
  decision_point: DecisionPoint
  subject_type: DecisionSubjectType
  subject_id: string
  reason: string
  basis_task_ids: string[]
  basis_metrics: Record<string, unknown>
  decided_by: string
  decided_by_id: string | null
  decided_at: string
  created_at: string
  selected_ids: string[]
  excluded_ids: string[]
  items: DecisionItem[]
}

/** 决策记录列表查询参数：后端 `Query(..., ge=1)` / `le=100` / `DP1`~`DP5`。 */
export interface DecisionListParams {
  page?: number
  page_size?: number
  decision_point?: DecisionPoint
}

/** 提交快照的一行（`DecisionSnapshotItem`）；分数未录时传 `null`。 */
export interface DecisionSnapshotInput {
  candidate_id: string
  score?: number | null
  rank?: number | null
}

/**
 * 提交一次决策（`DecisionCreate`）。
 *
 * 服务端要求 `reason` 非空白、`selected_ids` 与 `excluded_ids` 不能同时为空、
 * `snapshot` 非空且每个快照行都出现在结论里——这些规则在
 * `@/domain/decisions` 的 `buildDecisionCreatePayload` 里先挡一遍。
 */
export interface DecisionCreateParams {
  decision_point: DecisionPoint
  subject_type: DecisionSubjectType
  subject_id: string
  selected_ids: string[]
  excluded_ids: string[]
  basis_task_ids: string[]
  basis_metrics: Record<string, unknown>
  reason: string
  snapshot: DecisionSnapshotInput[]
}

/** 阶段缺口提示（`compute_project_stage` 的 `gaps[]`）。 */
export interface StageGap {
  code: string
  message: string
  action: string
  /** 目标路由；后端在没有对应页面时给 `null`，前端据此决定是否渲染跳转。 */
  link: string | null
}

/** 阶段计数器（后端是 `docs/05` §3.2 的超集，P-04 统计卡也复用它）。 */
export interface StageCounters {
  targets: number
  structures: number
  selected_pockets: number
  candidates: number
  submitted_tasks: number
  finished_tasks: number
  decisions: number
}

/** 研发阶段（`GET /projects/{id}/stage`，camelCase）。 */
export interface ProjectStage {
  currentStage: string
  stageName: string
  reachedStages: string[]
  nextStage: string | null
  gaps: StageGap[]
  counters: StageCounters
}
