import { test } from 'vitest'
import assert from 'node:assert/strict'

import {
  ARTIFACT_TYPE_LABEL_KEYS,
  artifactTypeLabelKey,
  buildArtifactDisplay,
  isFileNameLike,
  normalizeArtifactTypeCode
} from './presentation'

const translate = (key: string): string =>
  ({
    'artifacts.type.moleculeTable': '分子表',
    'artifacts.type.bindingPocket': '结合口袋',
    'artifacts.type.runReport': '运行报告',
    'artifacts.type.unknown': '其他产物'
  })[key] ?? key

test('受控类型码都有文案键，且 @version 后缀被剥掉', () => {
  assert.equal(Object.keys(ARTIFACT_TYPE_LABEL_KEYS).length, 8)
  assert.equal(normalizeArtifactTypeCode('molecule_table@2'), 'molecule_table')
  assert.equal(artifactTypeLabelKey('molecule_table@1'), 'artifacts.type.moleculeTable')
  assert.equal(artifactTypeLabelKey('binding_pocket'), 'artifacts.type.bindingPocket')
})

test('未知类型退到 unknown，不抛错也不返回空', () => {
  assert.equal(artifactTypeLabelKey('pocket.pdb'), 'artifacts.type.unknown')
  assert.equal(artifactTypeLabelKey(undefined), 'artifacts.type.unknown')
  assert.equal(artifactTypeLabelKey(''), 'artifacts.type.unknown')
})

test('isFileNameLike 只把「带扩展名且无空格」当文件名', () => {
  assert.equal(isFileNameLike('cb_data_result.csv'), true)
  assert.equal(isFileNameLike('pocket_1.pdb'), true)
  assert.equal(isFileNameLike('对接结果-1uw6'), false)
  assert.equal(isFileNameLike('EGFR 口袋分析'), false)
  assert.equal(isFileNameLike(''), false)
  assert.equal(isFileNameLike(null), false)
})

test('name 是文件名时不用它当标题，改「类型名 · v版本」', () => {
  const display = buildArtifactDisplay(
    {
      name: 'cb_data_result.csv',
      artifactType: 'molecule_table',
      standardType: null,
      semanticType: 'molecule_table',
      version: 2,
      filename: 'cb_data_result.csv'
    },
    translate
  )

  assert.equal(display.title, '分子表 · v2')
  assert.equal(display.typeKey, 'artifacts.type.moleculeTable')
  assert.equal(display.fileName, 'cb_data_result.csv')
})

test('name 是可读标题时保留标题，文件名仍可单独展示', () => {
  const display = buildArtifactDisplay(
    {
      name: 'EGFR 口袋预测结果',
      artifactType: 'binding_pocket',
      version: 1,
      filename: 'pocket_1.pdb'
    },
    translate
  )

  assert.equal(display.title, 'EGFR 口袋预测结果')
  assert.equal(display.typeKey, 'artifacts.type.bindingPocket')
  assert.equal(display.fileName, 'pocket_1.pdb')
})

test('没有 name 时退回类型名，且无版本时不带后缀', () => {
  const display = buildArtifactDisplay({ artifactType: 'run_report' }, translate)
  assert.equal(display.title, '运行报告')
  assert.equal(display.fileName, null)
})

test('标准类型优先于语义类型与产物类型', () => {
  const display = buildArtifactDisplay(
    { artifactType: 'ligand_structure', semanticType: 'molecule_table', standardType: 'binding_pocket@1' },
    translate
  )
  assert.equal(display.typeCode, 'binding_pocket')
  assert.equal(display.typeKey, 'artifacts.type.bindingPocket')
})
