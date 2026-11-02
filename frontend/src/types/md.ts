/**
 * 中国医药交付线 —— MD（分子动力学）与自由能页面类型定义。
 *
 * 与契约 docs/06-UI交互与原型说明.md 与 docs/05-API接口规格说明书.md
 * 保持一致，不得改变字段名（slug、参数、产物列名、file role）。
 */

import type { ProjectResultDetail } from './compounds'

/** P-26 提交表单的力场可选值（与后端工具参数枚举一致）。 */
export type MdForceField = 'amber99sb-ildn' | 'charmm36'

/** P-26 提交参数（字段名对齐冻结契约，勿改）。 */
export interface MdSubmitParams {
  force_field: MdForceField
  duration_ns: number
  temperature_k: number
  pressure_bar: number
  seed?: number
}

/** P-27 `md_trajectory@1` 产物四个 file role（顺序无关）。 */
export type MdTrajectoryRole =
  | 'topology_pdb'
  | 'trajectory_dcd'
  | 'analysis_csv'
  | 'metadata_json'

export const MD_TRAJECTORY_ROLES: readonly MdTrajectoryRole[] = [
  'topology_pdb',
  'trajectory_dcd',
  'analysis_csv',
  'metadata_json'
]

/**
 * P-27 analysis_csv 的标准列名（nanometer / ps / kelvin / kJ·mol⁻¹）。
 * 解析时容忍缺列，缺列对应值为 null。
 */
export interface MdAnalysisRow {
  time_ps: number
  rmsd_nm: number | null
  rmsf_nm: number | null
  rg_nm: number | null
  temperature_k: number | null
  potential_kj_mol: number | null
}

/** P-27 metadata_json 期望字段（全部可选，缺失时页面降级显示）。 */
export interface MdTrajectoryMetadata {
  total_frames?: number
  duration_ns?: number
  force_field?: string
  temperature_k?: number
  timestep_ps?: number
  [key: string]: unknown
}

/**
 * P-28 `molecule_table@1`（semantic_type `energies`）的标准列名。
 * ΔG 单位按 kJ·mol⁻¹。CSV 若无标准误列，用逐帧标准差真实计算。
 */
export interface FreeEnergyRow {
  frame: number
  delta_g_total: number | null
  delta_g_vdw: number | null
  delta_g_electrostatic: number | null
  delta_g_polar_solvation: number | null
  delta_g_nonpolar_solvation: number | null
  delta_g_sasa: number | null
}

/** 结果详情可能携带的 mock 标记；平台已不再展示 mock 提示，字段保留供排查历史数据。 */
export type MdResultDetail = ProjectResultDetail & { mock?: boolean }
