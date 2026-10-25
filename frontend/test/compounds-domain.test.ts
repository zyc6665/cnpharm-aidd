import { test } from 'vitest'
import assert from 'node:assert/strict'
import {
  MAX_COMPARE_CANDIDATES,
  PROPERTY_COLUMNS,
  buildComparisonMatrix,
  candidateLocationLabel,
  formatPropertyValue
} from '../src/domain/compounds'
import { sortResultsByFinishedDesc } from '../src/domain/results'

const SMALL_MOLECULE = 'SMALL_MOLECULE'

test('PROPERTY_COLUMNS 按固定顺序覆盖 7 项性质并带 i18n 标签键', () => {
  assert.deepEqual(
    PROPERTY_COLUMNS.map(column => column.key),
    ['mol_weight', 'logP', 'TPSA', 'HBD', 'HBA', 'RotB', 'QED']
  )
  assert.equal(PROPERTY_COLUMNS.length, 7)

  for (const column of PROPERTY_COLUMNS) {
    assert.ok(
      column.labelKey.startsWith('compounds.properties.'),
      `unexpected labelKey: ${column.labelKey}`
    )
    assert.equal(typeof column.digits, 'number')
  }
})

test('formatPropertyValue 对 null 与 undefined 统一返回短横线', () => {
  assert.equal(formatPropertyValue('logP', null), '-')
  assert.equal(formatPropertyValue('TPSA', undefined), '-')
  assert.equal(formatPropertyValue('mol_weight', null), '-')
  assert.equal(formatPropertyValue('QED', undefined), '-')
})

test('formatPropertyValue 对 QED 固定三位小数', () => {
  assert.equal(formatPropertyValue('QED', 0.85), '0.850')
  assert.equal(formatPropertyValue('QED', 0.123456), '0.123')
})

test('formatPropertyValue 对分子量固定三位小数', () => {
  assert.equal(formatPropertyValue('mol_weight', 342.2965), '342.296')
  assert.equal(formatPropertyValue('mol_weight', 18), '18.000')
  assert.equal(formatPropertyValue('mol_weight', 512.64), '512.640')
})

test('buildComparisonMatrix 对该列取值不全相同的行标红高亮', () => {
  const matrix = buildComparisonMatrix([
    { id: 'cand-1', name: 'A', candidate_type: SMALL_MOLECULE, mol_weight: 300.1, QED: 0.71 },
    { id: 'cand-2', name: 'B', candidate_type: SMALL_MOLECULE, mol_weight: 300.1, QED: 0.93 }
  ])

  assert.deepEqual(matrix.columns.map(column => column.id), ['cand-1', 'cand-2'])
  assert.equal(matrix.rows.length, PROPERTY_COLUMNS.length)

  const qed = matrix.rows.find(row => row.key === 'QED')
  assert.deepEqual(qed?.values, ['0.710', '0.930'])
  assert.deepEqual(qed?.highlight, [true, true])

  const molecularWeight = matrix.rows.find(row => row.key === 'mol_weight')
  assert.deepEqual(molecularWeight?.values, ['300.100', '300.100'])
  assert.deepEqual(molecularWeight?.highlight, [false, false])

  assert.equal(MAX_COMPARE_CANDIDATES, 6)
})

test('buildComparisonMatrix 在全列取值相同时不产生高亮', () => {
  const identical = {
    candidate_type: SMALL_MOLECULE,
    mol_weight: 512.6,
    logP: 2.5,
    TPSA: 63.6,
    HBD: 2,
    HBA: 6,
    RotB: 5,
    QED: 0.42
  }
  const matrix = buildComparisonMatrix([
    { id: 'cand-1', ...identical },
    { id: 'cand-2', ...identical }
  ])

  for (const row of matrix.rows) {
    assert.deepEqual(row.highlight, [false, false], `row ${row.key} should not be highlighted`)
  }
})

test('candidateLocationLabel 区分小分子与多肽位置', () => {
  assert.equal(
    candidateLocationLabel({ candidate_type: SMALL_MOLECULE }),
    'candidates.location.compound'
  )
  assert.equal(
    candidateLocationLabel({ candidate_type: 'PEPTIDE', peptide_sequence: 'ACDEFGHIK' }),
    'candidates.location.peptide'
  )
  assert.equal(
    candidateLocationLabel({ candidate_type: SMALL_MOLECULE, location: 'compound' }),
    'candidates.location.compound'
  )
})

test('sortResultsByFinishedDesc 按 finished_at 降序且 null 排最后', () => {
  const sorted = sortResultsByFinishedDesc([
    { task_id: 't-null', finished_at: null },
    { task_id: 't-old', finished_at: '2026-10-01T00:00:00Z' },
    { task_id: 't-undef' },
    { task_id: 't-new', finished_at: '2026-10-20T08:00:00Z' }
  ])

  assert.deepEqual(
    sorted.map(item => item.task_id),
    ['t-new', 't-old', 't-null', 't-undef']
  )
})
