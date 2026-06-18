export const WORKFLOW_ARTIFACT_SEMANTIC_TYPES = [
  'protein_pdb',
  'pocket_pdb',
  'generated_ligand',
  'ligand_pdb',
  'smiles_csv',
  'ranking_csv',
  'docking_pose',
  'docking_report',
  'affinity_report',
  'property_report',
  'optimized_lead'
] as const

export type WorkflowArtifactSemanticType = (typeof WORKFLOW_ARTIFACT_SEMANTIC_TYPES)[number]

export const WORKFLOW_ARTIFACT_SEMANTIC_ALIASES = {
  protein_structure: 'protein_pdb',
  pocket_structure: 'pocket_pdb'
} as const satisfies Readonly<Record<string, WorkflowArtifactSemanticType>>

export function normalizeWorkflowSemanticType(value: string): WorkflowArtifactSemanticType | string {
  return WORKFLOW_ARTIFACT_SEMANTIC_ALIASES[
    value as keyof typeof WORKFLOW_ARTIFACT_SEMANTIC_ALIASES
  ] ?? value
}
