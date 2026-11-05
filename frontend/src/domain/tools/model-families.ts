/**
 * 模型能力族（模型分类）的唯一前端展示映射。
 *
 * 后端按工具 slug 自动派生能力族，并在 `tool_categories` 中物化成分类行；
 * 前端只负责把 slug 翻译成当前语言，避免把中文名称硬编码进数据。
 */
export const MODEL_FAMILY_LABEL_KEYS: Record<string, string> = {
  structure_prediction: 'tools.modelFamilies.structure_prediction',
  pocket_prediction: 'tools.modelFamilies.pocket_prediction',
  molecule_generation: 'tools.modelFamilies.molecule_generation',
  peptide_design: 'tools.modelFamilies.peptide_design',
  admet_prediction: 'tools.modelFamilies.admet_prediction',
  property_prediction: 'tools.modelFamilies.property_prediction',
  affinity: 'tools.modelFamilies.affinity',
  free_energy: 'tools.modelFamilies.free_energy',
  docking: 'tools.modelFamilies.docking',
  molecular_dynamics: 'tools.modelFamilies.molecular_dynamics',
  toxicity_prediction: 'tools.modelFamilies.toxicity_prediction',
  protein_preparation: 'tools.modelFamilies.protein_preparation',
  ligand_preparation: 'tools.modelFamilies.ligand_preparation',
  conformer_generation: 'tools.modelFamilies.conformer_generation',
  format_conversion: 'tools.modelFamilies.format_conversion',
  synthetic_accessibility: 'tools.modelFamilies.synthetic_accessibility',
  interaction_analysis: 'tools.modelFamilies.interaction_analysis'
}

export function modelFamilyLabelKey(family?: string | null): string | null {
  if (!family) return null
  return MODEL_FAMILY_LABEL_KEYS[family] ?? null
}
