/**
 * 前端侧的模型能力族映射（后端 `model_family` 的兜底）。
 *
 * 正常情况下用 `/tools` 的 `contract.model_family`；若后端尚未升级/未重启、
 * 该字段缺失，则按已知 slug 兜底归组，保证「模型选择」仍能正确显示同类模型。
 * 新增模型时以后端注册 `model_family` 为准，无需改这里。
 */
export const MODEL_FAMILY_BY_SLUG: Record<string, string> = {
  'boltz2-structure-prediction': 'structure_prediction',
  'lvpocket-pocket-prediction': 'pocket_prediction',
  'pocket2mol-pocket-ligand-generation': 'molecule_generation',
  'therapainter-peptide-prediction': 'peptide_design',
  'molp-pc-property-prediction': 'admet_prediction',
  'builtin-admet-prediction': 'admet_prediction',
  'builtin-rdkit-properties': 'property_prediction',
  'builtin-toxicity-prediction': 'toxicity_prediction',
  'builtin-vina-docking': 'docking',
  'autodock-vina-docking': 'docking',
  'builtin-molecular-dynamics': 'molecular_dynamics',
  'gromacs-md': 'molecular_dynamics',
  'msign-affinity-prediction': 'affinity',
  'boltz2-affinity-prediction': 'affinity',
  'gmx-mmpbsa': 'free_energy',
}

export function resolveModelFamily(tool: {
  slug?: string
  contract?: { model_family?: string | null } | null
}): string | null {
  const fromContract = tool.contract?.model_family
  if (fromContract) return fromContract
  return tool.slug ? (MODEL_FAMILY_BY_SLUG[tool.slug] ?? null) : null
}
