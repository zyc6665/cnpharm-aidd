export const WORKFLOW_ARTIFACT_SEMANTIC_TYPES = [
  'protein_structure@1',
  'binding_pocket@1',
  'ligand_structure@1',
  'molecule_table@1',
  'run_report@1',
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
  protein_pdb: 'protein_structure@1',
  protein_structure: 'protein_structure@1',
  pocket_pdb: 'binding_pocket@1',
  pocket_structure: 'binding_pocket@1',
  generated_ligand: 'ligand_structure@1',
  ligand_pdb: 'ligand_structure@1',
  smiles_csv: 'molecule_table@1',
  ranking_csv: 'molecule_table@1'
} as const satisfies Readonly<Record<string, WorkflowArtifactSemanticType>>

export function normalizeWorkflowSemanticType(value: string): WorkflowArtifactSemanticType | string {
  return WORKFLOW_ARTIFACT_SEMANTIC_ALIASES[
    value as keyof typeof WORKFLOW_ARTIFACT_SEMANTIC_ALIASES
  ] ?? value
}
