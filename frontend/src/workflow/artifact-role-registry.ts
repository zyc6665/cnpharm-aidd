const ARTIFACT_ROLE_LABELS: Record<string, string> = {
  atom_pocket_pdb: '原子口袋 PDB',
  metadata_json: '元数据 JSON',
  pocket_metadata_json: '口袋元数据 JSON',
  preparation_report_json: '处理报告 JSON',
  prepared_pdb: '已处理 PDB',
  prepared_pqr: '已处理 PQR',
  raw_structure_file: '原始结构文件',
  receptor_pdbqt: '受体 PDBQT',
  report_json: '报告 JSON',
  report_markdown: '报告 Markdown',
  residue_pocket_pdb: '残基口袋 PDB',
  structure_2d_sdf: '2D 配体 SDF',
  structure_3d_sdf: '3D 配体 SDF',
  structure_file: '结构文件',
  table_file: '表格文件',
}

export function formatArtifactRole(role: string): string {
  const normalizedRole = String(role).trim()
  const label = ARTIFACT_ROLE_LABELS[normalizedRole]
  return label ? `${label} (${normalizedRole})` : normalizedRole
}

export function formatArtifactRoleList(roles: readonly string[]): string {
  return roles.map(formatArtifactRole).join('、')
}
