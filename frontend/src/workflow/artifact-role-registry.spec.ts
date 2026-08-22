import { describe, expect, it } from 'vitest'
import { formatArtifactRole, formatArtifactRoleList } from './artifact-role-registry'

describe('artifact-role-registry', () => {
  it('formats known artifact roles with readable labels and raw role ids', () => {
    expect(formatArtifactRole('receptor_pdbqt')).toBe('受体 PDBQT (receptor_pdbqt)')
    expect(formatArtifactRoleList(['prepared_pdb', 'structure_3d_sdf'])).toBe(
      '已处理 PDB (prepared_pdb)、3D 配体 SDF (structure_3d_sdf)'
    )
  })

  it('keeps unknown roles visible instead of hiding them', () => {
    expect(formatArtifactRole('custom_role')).toBe('custom_role')
  })
})
