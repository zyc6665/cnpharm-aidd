import type { TaskStatus } from '@/types/models'

/**
 * 「设计任务」汇总页的类别定义。
 *
 * 背景：侧边栏「设计工具」下的五个入口（分子生成 / 多肽设计 / 性质预测 /
 * 虚拟筛选 / 分子动力学）都是**提交页**。用户跑完一轮之后，想知道「我在这个项目
 * 跑过哪些设计任务、上次那批结果在哪」，只能去任务中心按工具逐个筛，或者凭记忆
 * 翻历史——这些任务在任务中心里和其他任务混在一起，看不出属于哪个设计环节。
 *
 * 这里把六类工具的 slug 与「结果页路由」绑在一起：列表里点一行能直接跳到该类别
 * 对应的结果页（分子表 / ADMET 矩阵 / 筛选漏斗 / MD 曲线 / 自由能），而不是先落到
 * 通用任务详情再自己找。
 *
 * slug 全部来自各域已冻结的契约常量（`types/design.ts`、`types/predict.ts`、
 * `types/screening.ts`、`api/md.ts`），此处只做集中引用，不重复声明字面量。
 */
import { MOLECULE_GENERATION_TOOL_SLUG, PEPTIDE_DESIGN_TOOL_SLUG } from '@/types/design'
import { ADMET_TOOL_SLUG } from '@/types/predict'
import { VINA_TOOL_SLUG } from '@/types/screening'
import { FREE_ENERGY_TOOL_SLUG, MD_TOOL_SLUG } from '@/api/md'

export interface DesignRunCategory {
  /** 页签 key，同时用于 i18n：`design.runs.category.<key>`。 */
  key: string
  slugs: readonly string[]
  /** 该类别任务的结果页路径；没有专属结果页的回到通用任务详情。 */
  resultPath: (taskId: string) => string
}

export const DESIGN_RUN_CATEGORIES: readonly DesignRunCategory[] = [
  {
    key: 'molecule',
    slugs: [MOLECULE_GENERATION_TOOL_SLUG],
    resultPath: taskId => `/tasks/${taskId}/results`
  },
  {
    key: 'peptide',
    slugs: [PEPTIDE_DESIGN_TOOL_SLUG],
    resultPath: taskId => `/tasks/${taskId}/results`
  },
  {
    key: 'predict',
    slugs: [ADMET_TOOL_SLUG],
    resultPath: taskId => `/tasks/${taskId}/predictions`
  },
  {
    key: 'screening',
    slugs: [VINA_TOOL_SLUG],
    resultPath: taskId => `/tasks/${taskId}/screening`
  },
  {
    key: 'md',
    slugs: [MD_TOOL_SLUG],
    resultPath: taskId => `/tasks/${taskId}/md`
  },
  {
    key: 'freeEnergy',
    slugs: [FREE_ENERGY_TOOL_SLUG],
    resultPath: taskId => `/tasks/${taskId}/free-energy`
  }
]

/** 「全部」页签用的 slug 合集，顺序与上面一致。 */
export const ALL_DESIGN_TOOL_SLUGS: readonly string[] = DESIGN_RUN_CATEGORIES.flatMap(
  category => category.slugs
)

export function findDesignRunCategory(toolSlug: string | undefined): DesignRunCategory | null {
  if (!toolSlug) return null
  return DESIGN_RUN_CATEGORIES.find(category => category.slugs.includes(toolSlug)) ?? null
}

/**
 * 一行任务的跳转目标：有专属结果页的类别去结果页，其余回通用任务详情。
 *
 * 失败 / 取消 / 超时也照样跳结果页——那些页面本来就处理了「没有产物」的状态，
 * 而且失败原因在结果页头部比任务详情更醒目。
 */
export function resolveDesignRunPath(toolSlug: string | undefined, taskId: string): string {
  const category = findDesignRunCategory(toolSlug)
  return category ? category.resultPath(taskId) : `/tasks/${taskId}`
}

/** 设计任务页签的「进行中」口径：还没出结果。 */
export const DESIGN_RUN_ACTIVE_STATUSES: readonly TaskStatus[] = ['pending', 'queued', 'running']
