// P-23 / P-24 / P-25 虚拟筛选：工具 slug、参数默认值与列名约定。
// 契约来源：docs/superpowers/plans/2026-10-28-mock-model-packages-and-remaining-pages.md（冻结）。

/** 契约规定的提交工具 slug（P-23）。 */
export const VINA_TOOL_SLUG = 'vina-virtual-screening'

/** 与后端 params 完全一致的漏斗参数（snake_case）。 */
export interface ScreeningParams {
  pharmacophore_min_features: number
  docking_score_cutoff: number
  exhaustiveness: number
  top_n: number
  seed: number
}

/** 契约默认值。 */
export const SCREENING_PARAM_DEFAULTS: ScreeningParams = {
  pharmacophore_min_features: 3,
  docking_score_cutoff: -8.0,
  exhaustiveness: 8,
  top_n: 100,
  seed: 42
}

/** 取值范围（用于表单控件与校验）。 */
export const SCREENING_PARAM_RANGES = {
  pharmacophore_min_features: { min: 1, max: 6 },
  docking_score_cutoff: { min: -14, max: -4 },
  exhaustiveness: { min: 1, max: 32 },
  top_n: { min: 1, max: 1000 },
  seed: { min: 0, max: 999999 }
} as const

/** ranked（molecule_table@1）契约列顺序。 */
export const SCREENING_RANKED_COLUMNS = [
  'smiles',
  'inchi_key',
  'mol_weight',
  'logp',
  'qed',
  'stage_pharmacophore',
  'stage_docking',
  'stage_rescore',
  'docking_score',
  'rank',
  'passes'
] as const

/** ranked 列 → i18n 文案键（位于 screening.result.* / screening.detail.*）。 */
export const SCREENING_RANKED_COLUMN_I18N: Record<string, string> = {
  smiles: 'colSmiles',
  inchi_key: 'colInchiKey',
  mol_weight: 'colMolWeight',
  logp: 'colLogp',
  qed: 'colQed',
  stage_pharmacophore: 'stagePharmacophore',
  stage_docking: 'stageDocking',
  stage_rescore: 'stageRescore',
  docking_score: 'dockingScore',
  rank: 'rank',
  passes: 'passes'
}

/** poses 元数据（ligand_structure@1 的 metadata_json）。 */
export interface PoseInteraction {
  residue: string
  chain?: string
  type: string
  distance: number
}

export interface PoseMetadata {
  pose_id: string
  ligand_smiles?: string
  rank: number
  docking_score: number
  rmsd_lb: number
  rmsd_ub: number
  interactions?: PoseInteraction[]
}

export interface PosesMetadata {
  poses: PoseMetadata[]
}
