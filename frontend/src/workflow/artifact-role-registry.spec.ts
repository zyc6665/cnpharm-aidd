import { describe, expect, it } from 'vitest'
import {
  formatArtifactRole,
  formatArtifactRoleList,
} from './artifact-role-registry'
import type { ArtifactRoleLabels } from './artifact-role-registry'

const testLabels: ArtifactRoleLabels = {
  roleNames: {
    prepared_pdb: '已处理 PDB',
    receptor_pdbqt: '受体 PDBQT',
    structure_3d_sdf: '3D 配体 SDF',
  },
  listSeparator: '、',
}

describe('artifact-role-registry', () => {
  it('formats known artifact roles with readable labels and raw role ids', () => {
    expect(formatArtifactRole('receptor_pdbqt', testLabels)).toBe('受体 PDBQT (receptor_pdbqt)')
    expect(formatArtifactRoleList(['prepared_pdb', 'structure_3d_sdf'], testLabels)).toBe(
      '已处理 PDB (prepared_pdb)、3D 配体 SDF (structure_3d_sdf)'
    )
  })

  it('allows callers to inject role labels and list separators', () => {
    const labels: ArtifactRoleLabels = {
      roleNames: {
        receptor_pdbqt: 'Receptor PDBQT',
        structure_3d_sdf: '3D Ligand SDF',
      },
      listSeparator: ' | ',
    }

    expect(formatArtifactRole('receptor_pdbqt', labels)).toBe('Receptor PDBQT (receptor_pdbqt)')
    expect(formatArtifactRoleList(['receptor_pdbqt', 'structure_3d_sdf'], labels)).toBe(
      'Receptor PDBQT (receptor_pdbqt) | 3D Ligand SDF (structure_3d_sdf)'
    )
  })

  it('keeps unknown roles visible instead of hiding them', () => {
    expect(formatArtifactRole('custom_role', testLabels)).toBe('custom_role')
  })
})
