import { describe, expect, it } from 'vitest'
import {
  buildMoleculeCsv,
  buildSdfExportText,
  readSdfRecordSmiles,
} from './molecule-export'

describe('结果 CSV 导出', () => {
  it('保留列顺序并转义逗号、引号和换行', () => {
    const csv = buildMoleculeCsv(
      [
        { key: 'smiles', title: 'SMILES' },
        { key: 'note', title: 'Note' },
      ],
      [
        { smiles: 'CCO', note: 'plain' },
        { smiles: 'CC(=O)O', note: 'a,b "quoted"' },
      ]
    )
    expect(csv.split('\r\n')[0]).toBe('SMILES,Note')
    expect(csv).toContain('"a,b ""quoted"""')
  })
})

describe('结果 SDF 导出', () => {
  const recordWith = (smiles: string) =>
    `mol\n  test\n\n  0  0  0  0  0  0  0  0  0  0999 V2000\nM  END\n> <SMILES>\n${smiles}\n\n$$$$\n`

  it('记录数与行数一致时按下标对应', () => {
    const text = buildSdfExportText(
      [recordWith('CCO'), recordWith('CCC')],
      [{ smiles: 'CCO' }, { smiles: 'CCC' }]
    )
    expect(text).toContain('CCO')
    expect(text).toContain('CCC')
    expect(text.match(/\$\$\$\$/g)).toHaveLength(2)
  })

  it('记录数与行数不一致时按 SMILES 属性匹配', () => {
    const text = buildSdfExportText(
      [recordWith('CCO'), recordWith('CCC')],
      [{ smiles: 'CCC' }]
    )
    expect(text).toContain('CCC')
    expect(text).not.toContain('CCO')
  })

  it('没有对应记录时生成仅属性记录，保留 SMILES', () => {
    const text = buildSdfExportText([], [{ smiles: 'CCN' }])
    expect(text).toContain('> <SMILES>')
    expect(text).toContain('CCN')
    expect(text.trimEnd().endsWith('$$$$')).toBe(true)
  })

  it('记录数与行数一致但顺序已重排时，仍优先按 SMILES 精确匹配', () => {
    const text = buildSdfExportText(
      [recordWith('CCO'), recordWith('CCC')],
      [{ smiles: 'CCC' }, { smiles: 'CCO' }]
    )
    const chunks = text.split('$$$$').filter(s => s.trim())
    expect(chunks).toHaveLength(2)
    expect(readSdfRecordSmiles(chunks[0] ?? '')).toBe('CCC')
    expect(readSdfRecordSmiles(chunks[1] ?? '')).toBe('CCO')
  })

  it('能从 SDF 记录里读出 SMILES 属性', () => {
    expect(readSdfRecordSmiles(recordWith('CC(=O)O'))).toBe('CC(=O)O')
  })
})
