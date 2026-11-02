// P-21 / P-22 性质预测：工具 slug、指标组枚举与列名约定。
// 契约来源：docs/06-UI交互与原型说明.md 与 docs/05-API接口规格说明书.md（冻结）。

/** 契约规定的提交工具 slug（P-21）。 */
export const ADMET_TOOL_SLUG = 'molp-pc-property-prediction'

/** 契约规定的 8 个指标组枚举，顺序即界面展示顺序。 */
export const PREDICT_TASK_GROUPS = [
  'Absorption',
  'Distribution',
  'Excretion',
  'Metabolism',
  'Toxicology',
  'Tox21',
  'Ecotoxicity',
  'LD50'
] as const

export type PredictTaskGroup = (typeof PREDICT_TASK_GROUPS)[number]

/** 指标组枚举 → i18n 文案键（位于 predict.submit.*）。 */
export const PREDICT_GROUP_I18N: Record<PredictTaskGroup, string> = {
  Absorption: 'groupAbsorption',
  Distribution: 'groupDistribution',
  Excretion: 'groupExcretion',
  Metabolism: 'groupMetabolism',
  Toxicology: 'groupToxicology',
  Tox21: 'groupTox21',
  Ecotoxicity: 'groupEcotoxicity',
  LD50: 'groupLD50'
}

/** 默认全选。 */
export const PREDICT_DEFAULT_TASK_GROUPS: PredictTaskGroup[] = [...PREDICT_TASK_GROUPS]

/**
 * molecule_table（properties）列名 → i18n 文案键（位于 predict.result.*）。
 * 契约列：smiles, inchi_key, mol_weight, logp, tpsa, hbd, hba, rotb, qed,
 * sa_score, admet_absorption … admet_ld50。
 */
export const PREDICT_COLUMN_I18N: Record<string, string> = {
  smiles: 'colSmiles',
  inchi_key: 'colInchiKey',
  mol_weight: 'colMolWeight',
  logp: 'colLogp',
  tpsa: 'colTpsa',
  hbd: 'colHbd',
  hba: 'colHba',
  rotb: 'colRotb',
  qed: 'colQed',
  sa_score: 'colSaScore',
  admet_absorption: 'colAdmetAbsorption',
  admet_distribution: 'colAdmetDistribution',
  admet_excretion: 'colAdmetExcretion',
  admet_metabolism: 'colAdmetMetabolism',
  admet_toxicity: 'colAdmetToxicity',
  admet_tox21: 'colAdmetTox21',
  admet_ecotoxicity: 'colAdmetEcotoxicity',
  admet_ld50: 'colAdmetLd50'
}

/** 非数值列：不参与直方图与数值排序。 */
export const PREDICT_TEXT_COLUMNS = ['smiles', 'inchi_key']

/** 预测结果表里用于矩阵展示的分子标识列。 */
export const PREDICT_MOLECULE_KEY_COLUMN = 'smiles'
