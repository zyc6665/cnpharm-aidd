import { describe, expect, it } from 'vitest'
import type { SchemaProperty } from '@/types/models'
import {
  getSdfConversionStatusText,
  getToolFileAccept,
  getToolRequestErrorMessage,
  shouldShowSdfToPdbConverter,
} from './detail-file-inputs'

describe('tool detail file input rules', () => {
  it('adds SDF accept token only for the MSign ligand PDB input', () => {
    const prop = { type: 'file', accept: '.pdb' } as SchemaProperty

    expect(
      getToolFileAccept({ key: 'ligand_pdb', property: prop, toolSlug: 'msign-affinity-prediction' })
    ).toBe('.pdb,.sdf')

    expect(getToolFileAccept({ key: 'protein_pdb', property: prop, toolSlug: 'other-tool' })).toBe(
      '.pdb'
    )
  })

  it('prefers ui accept metadata over plain accept', () => {
    const prop = { type: 'file', accept: '.txt', 'ui:accept': '.mol2' } as SchemaProperty & {
      'ui:accept': string
    }

    expect(getToolFileAccept({ key: 'ligand_pdb', property: prop, toolSlug: 'other-tool' })).toBe(
      '.mol2'
    )
  })

  it('detects nested ligand PDB fields for SDF conversion', () => {
    expect(shouldShowSdfToPdbConverter('msign-affinity-prediction', 'ligand_pdb')).toBe(true)
    expect(shouldShowSdfToPdbConverter('msign-affinity-prediction', 'input_files.ligand_pdb')).toBe(
      true
    )
    expect(shouldShowSdfToPdbConverter('msign-affinity-prediction', 'protein_pdb')).toBe(false)
    expect(shouldShowSdfToPdbConverter('other-tool', 'ligand_pdb')).toBe(false)
  })

  it('formats SDF conversion status text by priority', () => {
    expect(getSdfConversionStatusText({ error: 'bad sdf', loading: true })).toBe('bad sdf')
    expect(getSdfConversionStatusText({ loading: true })).toBe('正在转换 SDF，请稍候...')
    expect(getSdfConversionStatusText({ convertedFilename: 'ligand.pdb' })).toBe(
      '转换成功，已生成 ligand.pdb'
    )
    expect(getSdfConversionStatusText({})).toBe('')
  })

  it('extracts request error messages with a stable fallback', () => {
    expect(
      getToolRequestErrorMessage({
        response: { data: { message: 'conversion service unavailable' } },
      })
    ).toBe('conversion service unavailable')
    expect(getToolRequestErrorMessage(new Error('invalid sdf'))).toBe('invalid sdf')
    expect(getToolRequestErrorMessage({})).toBe('SDF 转 PDB 失败，请检查文件格式或后端转换服务')
  })
})
