export interface ArtifactRoleLabels {
  roleNames: Readonly<Record<string, string>>
  listSeparator: string
}

export const DEFAULT_ARTIFACT_ROLE_LABELS: ArtifactRoleLabels = {
  roleNames: {
    atom_pocket_pdb: 'Atom pocket PDB',
    metadata_json: 'Metadata JSON',
    pocket_metadata_json: 'Pocket metadata JSON',
    preparation_report_json: 'Preparation report JSON',
    prepared_pdb: 'Prepared PDB',
    prepared_pqr: 'Prepared PQR',
    raw_structure_file: 'Raw structure file',
    receptor_pdbqt: 'Receptor PDBQT',
    report_json: 'Report JSON',
    report_markdown: 'Report Markdown',
    residue_pocket_pdb: 'Residue pocket PDB',
    structure_2d_sdf: '2D ligand SDF',
    structure_3d_sdf: '3D ligand SDF',
    structure_file: 'Structure file',
    table_file: 'Table file',
  },
  listSeparator: ', ',
}

export function formatArtifactRole(
  role: string,
  labels: ArtifactRoleLabels = DEFAULT_ARTIFACT_ROLE_LABELS,
): string {
  const normalizedRole = String(role).trim()
  const label = labels.roleNames[normalizedRole]
  return label ? `${label} (${normalizedRole})` : normalizedRole
}

export function formatArtifactRoleList(
  roles: readonly string[],
  labels: ArtifactRoleLabels = DEFAULT_ARTIFACT_ROLE_LABELS,
): string {
  return roles.map(role => formatArtifactRole(role, labels)).join(labels.listSeparator)
}
