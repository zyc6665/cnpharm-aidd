import type { Task } from '@/types/models'
import { findDesignRunCategory } from '@/domain/design/runs'
import { toDisplayFileName } from './file-display'

/**
 * 任务结果页的渲染类型。后端按 tool slug 区分任务领域，前端只负责把它映射成
 * 「结果页用哪个视图」——不复制工具注册表，也不影响任务执行。
 */
export type TaskResultKind =
  | 'structure'
  | 'pocket'
  | 'generation'
  | 'predict'
  | 'screening'
  | 'md'
  | 'freeEnergy'
  | 'generic'

const CATEGORY_KIND: Record<string, TaskResultKind> = {
  structure: 'structure',
  pocket: 'pocket',
  molecule: 'generation',
  peptide: 'generation',
  predict: 'predict',
  screening: 'screening',
  md: 'md',
  freeEnergy: 'freeEnergy',
}

/**
 * 同一能力族里可能存在未进入设计类别的历史 slug（例如内置 Vina 与
 * autodock-vina 并存）。这里只补「结果视图相同」的别名，不新增任务类别。
 */
const KIND_ALIAS: Record<string, TaskResultKind> = {
  'builtin-vina-docking': 'screening',
}

export function resolveTaskResultKind(toolSlug: string | undefined): TaskResultKind {
  if (toolSlug && KIND_ALIAS[toolSlug]) return KIND_ALIAS[toolSlug]
  const category = findDesignRunCategory(toolSlug)
  return category ? (CATEGORY_KIND[category.key] ?? 'generic') : 'generic'
}

/**
 * 任务输出有两层：接口的 `outputs.result` 外层是执行信封，真正的产物在
 * `outputs.result.result`（result_version / artifacts / metrics）。
 */
export function getTaskResultEnvelope(task: Task | null | undefined): Record<string, unknown> | null {
  const raw = task?.outputs?.result
  if (!raw) return null
  const nested = raw.result
  if (nested && typeof nested === 'object' && !Array.isArray(nested)) {
    return nested as Record<string, unknown>
  }
  return raw
}

export function getTaskResultMetrics(task: Task | null | undefined): Record<string, unknown> {
  const envelope = getTaskResultEnvelope(task)
  const metrics = envelope?.metrics
  return metrics && typeof metrics === 'object' && !Array.isArray(metrics)
    ? (metrics as Record<string, unknown>)
    : {}
}

export interface TaskArtifactFileRef {
  path?: string
  sha256?: string
  content_type?: string | null
}

export interface TaskResultArtifact {
  name?: string | null
  type?: string
  files?: Record<string, TaskArtifactFileRef>
  metadata?: Record<string, unknown>
  summary?: Record<string, unknown>
  metrics?: Record<string, unknown>
}

export function getTaskResultArtifacts(task: Task | null | undefined): Record<string, TaskResultArtifact> {
  const envelope = getTaskResultEnvelope(task)
  const artifacts = envelope?.artifacts
  if (!artifacts || typeof artifacts !== 'object' || Array.isArray(artifacts)) return {}
  return artifacts as Record<string, TaskResultArtifact>
}

export interface PocketResultRow {
  id: string
  atomPdb?: string
  residuePdb?: string
  metadata?: string
}

/** 从口袋任务的 metrics.pockets 读出候选列表；没有时返回空数组。 */
export function getPocketResultRows(task: Task | null | undefined): PocketResultRow[] {
  const metrics = getTaskResultMetrics(task)
  const raw = metrics.pockets
  if (!Array.isArray(raw)) return []
  return raw
    .filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === 'object')
    .map((item, index) => ({
      id: String(item.id ?? item.pocket_id ?? `P${index + 1}`),
      atomPdb: typeof item.pdb === 'string' ? toDisplayFileName(item.pdb) : undefined,
      residuePdb:
        typeof item.residue_pdb === 'string' ? toDisplayFileName(item.residue_pdb) : undefined,
      metadata: typeof item.metadata === 'string' ? toDisplayFileName(item.metadata) : undefined,
    }))
}

export function getPocketCount(task: Task | null | undefined): number {
  const metrics = getTaskResultMetrics(task)
  const count = metrics.pocket_count
  if (typeof count === 'number') return count
  return getPocketResultRows(task).length
}
