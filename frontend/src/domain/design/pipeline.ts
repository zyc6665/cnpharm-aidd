/**
 * 设计视角的阶段映射（薄适配层，非并行真相）。
 *
 * 就绪判定的唯一真相是后端 `GET /projects/{id}/stage`（`compute_project_stage`）：
 * 它给出 S0–S6、`counters` 与 `gaps[]`。这里只把 S0–S6 归并成给用户看的 5 段设计流程，
 * 供「设计流程总览」与「设计任务」共用，避免各处各自解释 counts/gaps 而口径漂移。
 */
import type { ProjectStage, StageCounters, StageGap } from '@/types/decisions'

export type DesignStageKey = 'structure' | 'pocket' | 'molecule' | 'evaluation' | 'validation'
export type StageReadiness = 'ready' | 'missing' | 'empty'

export interface DesignStageDef {
  key: DesignStageKey
  order: number
  /** i18n 键，如 `design.pipeline.stage.structure`。 */
  labelKey: string
  counterKey: keyof StageCounters
  /** 该阶段缺失时后端会给出的 gap code（用于取 gap 的文案与跳转）。 */
  gapCode: string
  defaultPath: (projectId: string) => string
}

export const DESIGN_STAGES: readonly DesignStageDef[] = [
  {
    key: 'structure',
    order: 1,
    labelKey: 'design.pipeline.stage.structure',
    counterKey: 'structures',
    gapCode: 'NO_STRUCTURE',
    defaultPath: projectId => `/projects/${projectId}/targets`,
  },
  {
    key: 'pocket',
    order: 2,
    labelKey: 'design.pipeline.stage.pocket',
    counterKey: 'selected_pockets',
    gapCode: 'NO_POCKET_SELECTED',
    defaultPath: projectId => `/projects/${projectId}/targets`,
  },
  {
    key: 'molecule',
    order: 3,
    labelKey: 'design.pipeline.stage.molecule',
    counterKey: 'candidates',
    gapCode: 'NO_CANDIDATE',
    defaultPath: projectId => `/design/molecules?project_id=${projectId}`,
  },
  {
    key: 'evaluation',
    order: 4,
    labelKey: 'design.pipeline.stage.evaluation',
    counterKey: 'submitted_tasks',
    gapCode: 'NO_TASK',
    defaultPath: projectId => `/predict?project_id=${projectId}`,
  },
  {
    key: 'validation',
    order: 5,
    labelKey: 'design.pipeline.stage.validation',
    counterKey: 'finished_tasks',
    gapCode: 'NO_TASK',
    defaultPath: projectId => `/md?project_id=${projectId}`,
  },
]

export interface DesignStageState {
  key: DesignStageKey
  order: number
  labelKey: string
  readiness: StageReadiness
  count: number
  gap: StageGap | null
  primaryPath: string
}

export function buildDesignStages(
  stage: ProjectStage | null,
  projectId: string
): DesignStageState[] {
  return DESIGN_STAGES.map(def => {
    const count = stage ? (stage.counters[def.counterKey] ?? 0) : 0
    const gap = stage?.gaps.find(item => item.code === def.gapCode) ?? null
    const readiness: StageReadiness =
      stage === null ? 'empty' : count > 0 ? 'ready' : 'missing'
    return {
      key: def.key,
      order: def.order,
      labelKey: def.labelKey,
      readiness,
      count,
      gap,
      primaryPath: gap?.link ?? def.defaultPath(projectId),
    }
  })
}

/** 第一个「未就绪」的阶段（ready 之外都算），用于「下一步」提示。 */
export function firstMissingStage(
  states: readonly DesignStageState[]
): DesignStageState | null {
  return states.find(state => state.readiness !== 'ready') ?? null
}
