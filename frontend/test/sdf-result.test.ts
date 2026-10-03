import { test } from 'vitest'
import assert from 'node:assert/strict'

import type { VisualizationSceneEntry } from '../src/domain/tasks/result-visualization.ts'
import {
  createNormalizedSdfObjectUrl,
  expandSdfOutputEntries,
  splitSdfRecords
} from '../src/domain/tasks/sdf-result.ts'

test('splitSdfRecords 应识别多分子 SDF 中的每个记录', () => {
  const text = [
    '',
    '     RDKit          3D',
    '',
    ' 18 23  0  0  0  0  0  0  0  0999 V2000',
    'M  END',
    '$$$$',
    '',
    '',
    '     RDKit          3D',
    '',
    ' 16 31  0  0  0  0  0  0  0  0999 V2000',
    'M  END',
    '$$$$'
  ].join('\n')

  const records = splitSdfRecords(text)

  assert.equal(records.length, 2)
  assert.equal(records[0]?.startsWith('\n     RDKit          3D\n\n'), true)
  assert.equal(records[0]?.split('\n')[3], ' 18 23  0  0  0  0  0  0  0  0999 V2000')
  assert.equal(records[1]?.startsWith('\n\n     RDKit          3D\n\n'), true)
  assert.equal(records[1]?.split('\n')[4], ' 16 31  0  0  0  0  0  0  0  0999 V2000')
  assert.equal(records[1]?.endsWith('$$$$\n'), true)
})

test('expandSdfOutputEntries 应将多分子 SDF 展开成多个可切换输出', async () => {
  const entry: VisualizationSceneEntry = {
    key: 'output-1',
    url: '/api/v1/files/output-1/download',
    label: 'generated_molecules.sdf',
    source: 'output',
    role: 'ligand',
    format: 'sdf',
    extension: '.sdf'
  }
  const blobs: Blob[] = []

  const result = await expandSdfOutputEntries([entry], {
    fetchText: async () => [
      '',
      '     RDKit          3D',
      '',
      ' 18 23  0  0  0  0  0  0  0  0999 V2000',
      'M  END',
      '$$$$',
      '',
      '',
      '     RDKit          3D',
      '',
      ' 16 31  0  0  0  0  0  0  0  0999 V2000',
      'M  END',
      '$$$$'
    ].join('\n'),
    objectUrl: {
      createObjectURL(blob) {
        blobs.push(blob)
        return `blob:mol-${blobs.length}`
      },
      revokeObjectURL() {
        return undefined
      }
    }
  })

  assert.equal(result.entries.length, 2)
  assert.equal(result.entries[0]?.label, 'generated_molecules.sdf #1')
  assert.equal(result.entries[1]?.label, 'generated_molecules.sdf #2')
  assert.equal(await blobs[0]?.text(), '\n     RDKit          3D\n\n 18 23  0  0  0  0  0  0  0  0999 V2000\nM  END\n$$$$\n')
  assert.equal(await blobs[1]?.text(), '\n\n     RDKit          3D\n\n 16 31  0  0  0  0  0  0  0  0999 V2000\nM  END\n$$$$\n')
})

test('expandSdfOutputEntries 应修复缺少 Molfile comment 行的单记录 SDF', async () => {
  const entry: VisualizationSceneEntry = {
    key: 'output-2',
    url: '/api/v1/files/output-2/download',
    label: 'ligand_001.sdf',
    source: 'output',
    role: 'ligand',
    format: 'sdf',
    extension: '.sdf'
  }
  const blobs: Blob[] = []

  const result = await expandSdfOutputEntries([entry], {
    fetchText: async () => [
      'RDKit          3D',
      '',
      '  5  4  0  0  0  0  0  0  0  0999 V2000',
      '  1.0000  2.0000  3.0000 C   0  0  0  0  0  0  0  0  0  0  0  0',
      'M  END',
      '$$$$'
    ].join('\n'),
    objectUrl: {
      createObjectURL(blob) {
        blobs.push(blob)
        return `blob:mol-${blobs.length}`
      },
      revokeObjectURL() {
        return undefined
      }
    }
  })

  assert.equal(result.entries.length, 1)
  assert.equal(result.entries[0]?.key, entry.key)
  assert.equal(result.entries[0]?.url, 'blob:mol-1')
  assert.equal(await blobs[0]?.text(), [
    'RDKit          3D',
    '',
    '',
    '  5  4  0  0  0  0  0  0  0  0999 V2000',
    '  1.0000  2.0000  3.0000 C   0  0  0  0  0  0  0  0  0  0  0  0',
    'M  END',
    '$$$$'
  ].join('\n') + '\n')
})

test('createNormalizedSdfObjectUrl 只为当前 SDF 创建规范化 Blob URL', async () => {
  const blobs: Blob[] = []
  const resource = await createNormalizedSdfObjectUrl('/api/v1/files/output-3/download', {
    fetchText: async () => [
      'RDKit          3D',
      '',
      '  1  0  0  0  0  0  0  0  0  0999 V2000',
      '   1.0000   2.0000   3.0000 C   0  0  0  0  0  0  0  0  0  0  0  0',
      'M  END',
      '$$$$'
    ].join('\n'),
    objectUrl: {
      createObjectURL(blob) {
        blobs.push(blob)
        return 'blob:selected-sdf'
      },
      revokeObjectURL() {
        return undefined
      }
    }
  })

  assert.equal(resource.url, 'blob:selected-sdf')
  assert.equal(blobs.length, 1)
  assert.equal((await blobs[0]?.text()).split('\n')[2], '')
})
