import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { DesignTableRow } from '@/types/design'

const { fetchProtectedFileText } = vi.hoisted(() => ({ fetchProtectedFileText: vi.fn() }))
vi.mock('@/utils/protected-file-access', () => ({ fetchProtectedFileText }))

import { findGenerationRowStructure } from './generation-viewer'
import type { Task } from '@/types/models'

describe('findGenerationRowStructure', () => {
  beforeEach(() => fetchProtectedFileText.mockReset())
  it('matches a unique row by SDF SMILES and scopes the result record', async () => {
    fetchProtectedFileText.mockResolvedValue('mol1\n  test\n\n  0  0  0  0  0  0  0  0  0  0999 V2000\nM  END\n> <SMILES>\nCCO\n\n$$$$\nmol2\n  test\n\n  0  0  0  0  0  0  0  0  0  0999 V2000\nM  END\n> <SMILES>\nCCN\n\n$$$$\n')
    const task = { output_files: [{ id: 'f1', filename: 'ligands.sdf', url: '/file' }] } as unknown as Task
    const rows = [{ __rowKey: '0', smiles: 'CCO' }, { __rowKey: '1', smiles: 'CCN' }] as DesignTableRow[]
    const match = await findGenerationRowStructure(task, rows[0]!, rows)
    expect(match?.sdfRecordIndex).toBe(0)
    expect(match?.sdfRecordScoped).toBe(true)
    expect(match?.sdfText).toContain('CCO')
  })
  it('does not claim a match when row SMILES are duplicated', async () => {
    fetchProtectedFileText.mockResolvedValue('mol\n  test\n\n  0  0  0  0  0  0  0  0  0  0999 V2000\nM  END\n> <SMILES>\nCCO\n\n$$$$\n')
    const task = { output_files: [{ id: 'f1', filename: 'ligands.sdf', url: '/file' }] } as unknown as Task
    const rows = [{ __rowKey: '0', smiles: 'CCO' }, { __rowKey: '1', smiles: 'CCO' }] as DesignTableRow[]
    expect(await findGenerationRowStructure(task, rows[0]!, rows)).toBeNull()
  })
})
