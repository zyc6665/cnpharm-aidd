import { beforeEach, describe, expect, it, vi } from 'vitest'

const { uploadFile } = vi.hoisted(() => ({ uploadFile: vi.fn() }))
vi.mock('@/api/files', () => ({ uploadFile }))

import { isValidHandoffSmiles, uploadMoleculeHandoff } from './result-handoff'

describe('molecule result handoff', () => {
  beforeEach(() => uploadFile.mockReset().mockResolvedValue({ data: { id: 'file-1' } }))

  it('rejects blanks, placeholders, invalid characters, and unbalanced groups', () => {
    for (const smiles of ['', '  ', 'N/A', 'not smiles', 'C(', 'C)', 'C[CH3', 'C=']) {
      expect(isValidHandoffSmiles(smiles)).toBe(false)
    }
  })

  it('accepts ordinary SMILES including explicit zero-charge and ring syntax', () => {
    for (const smiles of ['CCO', 'C1CCCCC1', '[NH4+]', 'C[C@H](O)C(=O)O']) {
      expect(isValidHandoffSmiles(smiles)).toBe(true)
    }
  })

  it('uploads a CSV with molecule ids when supplied', async () => {
    await expect(uploadMoleculeHandoff([{ smiles: ' CCO ', moleculeId: 'M1' }], 'handoff.csv'))
      .resolves.toEqual({ file_id: 'file-1', filename: 'handoff.csv' })
    const file = uploadFile.mock.calls[0]?.[0] as File
    expect(file.name).toBe('handoff.csv')
    await expect(file.text()).resolves.toContain('smiles,molecule_id\r\nCCO,M1')
  })
})
