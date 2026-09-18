import type { ArtifactRoleLabels } from './artifact-role-registry'

type ArtifactRoleTranslate = (key: string) => string

const ARTIFACT_ROLE_KEYS = [
  'atom_pocket_pdb',
  'metadata_json',
  'pocket_metadata_json',
  'preparation_report_json',
  'prepared_pdb',
  'prepared_pqr',
  'raw_structure_file',
  'receptor_pdbqt',
  'report_json',
  'report_markdown',
  'residue_pocket_pdb',
  'structure_2d_sdf',
  'structure_3d_sdf',
  'structure_file',
  'table_file',
] as const

export function buildArtifactRoleLabels(t: ArtifactRoleTranslate): ArtifactRoleLabels {
  const roleNames: Record<string, string> = {}
  for (const role of ARTIFACT_ROLE_KEYS) {
    roleNames[role] = t(`workflow.artifactRoles.${role}`)
  }

  return {
    roleNames,
    listSeparator: t('workflow.autoRepair.roleSeparator'),
  }
}
