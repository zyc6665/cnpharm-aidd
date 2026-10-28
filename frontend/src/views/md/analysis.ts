/**
 * P-27 / P-28 展示用的纯函数（无副作用、可在 node 环境直接测试）。
 *
 * 约定：
 * - 所有数值列都以列名（契约冻结）读取，缺列返回 null。
 * - ΔG 单位 kJ·mol⁻¹；标准差默认取样本标准差（n-1）。
 */

import type { ResultOutputArtifact } from '@/types/compounds'
import type { FreeEnergyRow, MdAnalysisRow } from '@/types/md'

/** 把任意输入转成有限数字；无法转换返回 null（不把 0 当缺失）。 */
export function toFiniteNumber(value: unknown): number | null {
  if (typeof value === 'number') return Number.isFinite(value) ? value : null
  if (typeof value === 'string') {
    const trimmed = value.trim()
    if (trimmed === '') return null
    const parsed = Number(trimmed)
    return Number.isFinite(parsed) ? parsed : null
  }
  return null
}

/** 算术平均；空数组返回 NaN 由调用方判断。 */
export function computeMean(values: number[]): number {
  if (values.length === 0) return Number.NaN
  const sum = values.reduce((acc, value) => acc + value, 0)
  return sum / values.length
}

/**
 * 标准差。默认样本标准差（除以 n-1，统计推断用）；
 * population=true 时用总体标准差（除以 n）。
 */
export function computeStdDev(values: number[], options: { sample?: boolean } = {}): number {
  const sample = options.sample ?? true
  const n = values.length
  if (n === 0) return Number.NaN
  if (n === 1) return 0
  const mean = computeMean(values)
  const variance =
    values.reduce((acc, value) => acc + (value - mean) ** 2, 0) / (sample ? n - 1 : n)
  return Math.sqrt(variance)
}

/** 标准误 = 样本标准差 / √n。 */
export function computeStandardError(values: number[]): number {
  const n = values.length
  if (n === 0) return Number.NaN
  if (n === 1) return 0
  return computeStdDev(values, { sample: true }) / Math.sqrt(n)
}

export interface DeltaGSummary {
  mean: number
  stdDev: number
  standardError: number
  frameCount: number
}

/** 汇总逐帧 ΔG：均值 / 样本标准差 / 标准误 / 帧数（忽略缺失值）。 */
export function summarizeDeltaG(values: Array<number | null>): DeltaGSummary {
  const finite = values.filter((value): value is number => typeof value === 'number' && Number.isFinite(value))
  if (finite.length === 0) {
    return { mean: Number.NaN, stdDev: Number.NaN, standardError: Number.NaN, frameCount: 0 }
  }
  return {
    mean: computeMean(finite),
    stdDev: computeStdDev(finite, { sample: true }),
    standardError: computeStandardError(finite),
    frameCount: finite.length
  }
}

/** 累计均值序列（收敛曲线）：第 i 个点 = 前 i+1 个值的平均。 */
export function cumulativeMean(values: Array<number | null>): number[] {
  const result: number[] = []
  let sum = 0
  let count = 0
  for (const value of values) {
    if (typeof value === 'number' && Number.isFinite(value)) {
      sum += value
      count += 1
    }
    result.push(count === 0 ? Number.NaN : sum / count)
  }
  return result
}

export type FreeEnergyComponentKey =
  | 'delta_g_vdw'
  | 'delta_g_electrostatic'
  | 'delta_g_polar_solvation'
  | 'delta_g_nonpolar_solvation'
  | 'delta_g_sasa'

export const FREE_ENERGY_COMPONENT_KEYS: readonly FreeEnergyComponentKey[] = [
  'delta_g_vdw',
  'delta_g_electrostatic',
  'delta_g_polar_solvation',
  'delta_g_nonpolar_solvation',
  'delta_g_sasa'
]

export interface EnergyComponentMean {
  key: FreeEnergyComponentKey
  mean: number
  count: number
}

/** 各能量组分在逐帧上的均值（bar chart 数据源）。 */
export function energyComponentMeans(rows: FreeEnergyRow[]): EnergyComponentMean[] {
  return FREE_ENERGY_COMPONENT_KEYS.map((key) => {
    const finite = rows
      .map((row) => row[key])
      .filter((value): value is number => typeof value === 'number' && Number.isFinite(value))
    return {
      key,
      mean: finite.length === 0 ? Number.NaN : computeMean(finite),
      count: finite.length
    }
  })
}

/** 从 papaparse 的原始行构造 MD 分析行（要求 time_ps 有效）。 */
export function buildAnalysisRows(raw: Array<Record<string, unknown>>): MdAnalysisRow[] {
  const rows: MdAnalysisRow[] = []
  for (const item of raw) {
    const time = toFiniteNumber(item.time_ps)
    if (time === null) continue
    rows.push({
      time_ps: time,
      rmsd_nm: toFiniteNumber(item.rmsd_nm),
      rmsf_nm: toFiniteNumber(item.rmsf_nm),
      rg_nm: toFiniteNumber(item.rg_nm),
      temperature_k: toFiniteNumber(item.temperature_k),
      potential_kj_mol: toFiniteNumber(item.potential_kj_mol)
    })
  }
  return rows
}

/** 从 papaparse 的原始行构造自由能逐帧行（frame 缺失时用行号兜底）。 */
export function buildFreeEnergyRows(raw: Array<Record<string, unknown>>): FreeEnergyRow[] {
  return raw.map((item, index) => {
    const frame = toFiniteNumber(item.frame)
    return {
      frame: frame ?? index + 1,
      delta_g_total: toFiniteNumber(item.delta_g_total),
      delta_g_vdw: toFiniteNumber(item.delta_g_vdw),
      delta_g_electrostatic: toFiniteNumber(item.delta_g_electrostatic),
      delta_g_polar_solvation: toFiniteNumber(item.delta_g_polar_solvation),
      delta_g_nonpolar_solvation: toFiniteNumber(item.delta_g_nonpolar_solvation),
      delta_g_sasa: toFiniteNumber(item.delta_g_sasa)
    }
  })
}

/**
 * 曲线抽样：点数超过 maxPoints 时均匀抽稀（保留首尾），用于大轨迹降采样。
 */
export function downsampleSeries<T>(items: T[], maxPoints: number): T[] {
  if (maxPoints <= 0 || items.length <= maxPoints) return items.slice()
  if (maxPoints === 1) return [items[0] as T]
  const step = (items.length - 1) / (maxPoints - 1)
  const result: T[] = []
  for (let i = 0; i < maxPoints; i += 1) {
    const index = Math.round(i * step)
    result.push(items[index] as T)
  }
  return result
}

function escapeCsvCell(value: unknown): string {
  if (value === null || value === undefined) return ''
  const text = String(value)
  if (/[",\n\r]/.test(text)) {
    return `"${text.replace(/"/g, '""')}"`
  }
  return text
}

/** 按列顺序生成 CSV 文本（用于导出）。 */
export function rowsToCsv(rows: Array<Record<string, unknown>>, columns: string[]): string {
  const header = columns.map(escapeCsvCell).join(',')
  const body = rows.map((row) => columns.map((column) => escapeCsvCell(row[column])).join(','))
  return [header, ...body].join('\n')
}

export interface MdEstimateInput {
  durationNs: number
  gpuCount: number
  /** 单卡吞吐，默认 20 ns/day（粗估）。 */
  nsPerDayPerGpu?: number
}

/**
 * 粗略估算 MD 耗时（小时）。仅用于提示，不是承诺。
 * hours = duration_ns / (gpu_count * ns_per_day_per_gpu) * 24
 */
export function estimateMdRuntimeHours(input: MdEstimateInput): number {
  const { durationNs, gpuCount } = input
  const nsPerDayPerGpu = input.nsPerDayPerGpu ?? 20
  if (!(durationNs > 0) || !(gpuCount > 0) || !(nsPerDayPerGpu > 0)) return Number.NaN
  const hours = (durationNs / (gpuCount * nsPerDayPerGpu)) * 24
  return Math.round(hours * 10) / 10
}

/** 在结果产物里按标准类型（含版本前缀）定位产物。 */
export function findOutputByStandardType(
  outputs: ResultOutputArtifact[],
  standardType: string
): ResultOutputArtifact | null {
  const exact = outputs.find((output) => output.standard_type === standardType)
  if (exact) return exact
  const base = standardType.split('@')[0]
  const byPrefix = outputs.find(
    (output) =>
      typeof output.standard_type === 'string' &&
      (output.standard_type === base || output.standard_type.startsWith(`${base}@`))
  )
  return byPrefix ?? null
}

/** 从分析行中抽取某一数值列（跳过缺失值）。 */
export function seriesValues(rows: MdAnalysisRow[], key: keyof MdAnalysisRow): number[] {
  return rows
    .map((row) => row[key])
    .filter((value): value is number => typeof value === 'number' && Number.isFinite(value))
}
