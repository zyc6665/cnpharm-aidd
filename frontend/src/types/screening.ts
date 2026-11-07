// P-23 / P-24 / P-25 虚拟筛选：工具 slug、参数默认值与列名约定。
// 契约来源：autodock-vina-docking 1.1.0 的 tool_versions.parameters_schema。

/** 契约规定的提交工具 slug（P-23）。 */
export const VINA_TOOL_SLUG = 'autodock-vina-docking'

/** 与后端 params 完全一致的筛选参数（snake_case）。 */
export interface ScreeningParams {
  box_size: number
  exhaustiveness: number
  n_poses: number
  pharmacophore_min_features: number
  docking_score_cutoff: number
  top_n: number
  seed: number
}

/** 契约默认值。 */
export const SCREENING_PARAM_DEFAULTS: ScreeningParams = {
  box_size: 22,
  exhaustiveness: 8,
  n_poses: 9,
  pharmacophore_min_features: 3,
  docking_score_cutoff: -8.0,
  top_n: 100,
  seed: 42
}

/** 取值范围（用于表单控件与校验）。 */
export const SCREENING_PARAM_RANGES = {
  box_size: { min: 10, max: 40 },
  exhaustiveness: { min: 1, max: 32 },
  n_poses: { min: 1, max: 20 },
  pharmacophore_min_features: { min: 0, max: 8 },
  docking_score_cutoff: { min: -20, max: 0 },
  top_n: { min: 1, max: 10000 },
  seed: { min: 0, max: 999999 }
} as const

/**
 * ranked（molecule_table@1）契约列顺序。与 Vina 1.1.0 `docking_results.csv`
 * 一一对应：每行保留层层通过标记、打分与失败原因，最终保留 `passes=true`。
 */
export const SCREENING_RANKED_COLUMNS = [
  'molecule_id',
  'smiles',
  'pharmacophore_features',
  'stage_pharmacophore',
  'stage_docking',
  'docking_score',
  'stage_cutoff',
  'rank',
  'passes',
  'mol_weight',
  'logp',
  'tpsa',
  'qed',
  'rmsd_lb',
  'rmsd_ub',
  'num_poses',
  'error'
] as const

/** ranked 列 → i18n 文案键（位于 screening.result.* / screening.detail.*）。 */
export const SCREENING_RANKED_COLUMN_I18N: Record<string, string> = {
  molecule_id: 'colMoleculeId',
  smiles: 'colSmiles',
  pharmacophore_features: 'colPharmacophoreFeatures',
  stage_pharmacophore: 'stagePharmacophore',
  stage_docking: 'stageDocking',
  docking_score: 'dockingScore',
  stage_cutoff: 'stageCutoff',
  rank: 'rank',
  passes: 'passes',
  mol_weight: 'colMolWeight',
  logp: 'colLogp',
  tpsa: 'colTpsa',
  qed: 'colQed',
  rmsd_lb: 'colRmsdLb',
  rmsd_ub: 'colRmsdUb',
  num_poses: 'colNumPoses',
  error: 'colError'
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
