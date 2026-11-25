import { describe, expect, it } from 'vitest'
import {
  buildMoleculeCsv,
  buildSdfExportText,
  readSdfRecordSmiles,
} from './molecule-export'

describe('结果 CSV 导出', () => {
  it('保留列顺序并转义逗号、引号和换行', () => {
    const csv = buildMoleculeCsv(
      [{ key: 'smiles', title: 'SMILES' }, { key: 'note', title: 'Note' }],
      [{ smiles: 'CCO', note: 'plain' }, { smiles: 'CC(=O)O', note: 'a,b "quoted"' }]
    )
    expect(csv.split('\r\n')[0]).toBe('SMILES,Note')
    expect(csv).toContain('"a,b ""quoted"""')
  })
})

describe('结果 SDF 导出', () => {
  const recordWith = (smiles: string) =>
    `mol\n  test\n\n  0  0  0  0  0  0  0  0  0  0999 V2000\nM  END\n> <SMILES>\n${smiles}\n\n$$$$\n`

  it('按唯一 SMILES 属性匹配并允许行重排', () => {
    const text = buildSdfExportText([recordWith('CCO'), recordWith('CCC')], [{ smiles: 'CCC' }, { smiles: 'CCO' }])
    const chunks = text.split('$$$$').filter(s => s.trim())
    expect(chunks).toHaveLength(2)
    expect(readSdfRecordSmiles(chunks[0] ?? '')).toBe('CCC')
    expect(readSdfRecordSmiles(chunks[1] ?? '')).toBe('CCO')
  })

  it('omits unmatched and ambiguous records instead of inventing positional matches or stubs', () => {
    const text = buildSdfExportText([recordWith('CCO')], [{ smiles: 'CCN' }])
    expect(text).toBe('')
    expect(buildSdfExportText([recordWith('CCO'), recordWith('CCO')], [{ smiles: 'CCO' }])).toBe('')
  })

  it('disambiguates shared-SMILES conformers when unique moleculeId matches record identity', () => {
    const pose1 = `pose_1\n  test\n\n  0  0  0  0  0  0  0  0  0  0999 V2000\nM  END\n> <SMILES>\nCCO\n\n$$$$\n`
    const pose2 = `pose_2\n  test\n\n  0  0  0  0  0  0  0  0  0  0999 V2000\nM  END\n> <SMILES>\nCCO\n\n$$$$\n`
    const text = buildSdfExportText([pose1, pose2], [{ smiles: 'CCO', moleculeId: 'pose_2' }])
    expect(text).toContain('pose_2')
    expect(text).not.toContain('pose_1')
  })

  it('能从 SDF 记录里读出 SMILES 属性', () => {
    expect(readSdfRecordSmiles(recordWith('CC(=O)O'))).toBe('CC(=O)O')
  })
})
