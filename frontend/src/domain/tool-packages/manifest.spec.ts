import { test } from 'vitest'
import assert from 'node:assert/strict'
import type { ToolPackage } from '@/types/tool-packages'
import {
  formatToolPackageManifest,
  getToolPackageArtifactSlots,
  getToolPackageContractSummary,
  getToolPackageManifest,
  getToolPackageValidationColor,
  getToolPackageValidationErrors,
  getToolPackageVariantSummary
} from './manifest'

function toolPackage(overrides: Partial<ToolPackage> = {}): ToolPackage {
  return {
    id: 'package-1',
    slug: 'molp-pc',
    name: 'MolP-PC',
    status: 'draft',
    owner_id: 'user-1',
    current_version: {
      id: 'version-1',
      version: '1.0.0',
      manifest_digest: 'sha256:abc',
      signature: 'cosign:abc',
      is_signed: true,
      validation_status: 'valid',
      validation_errors: [],
      manifest: {
        artifacts: {
          inputs: [{ name: 'protein', type: 'pdb' }],
          outputs: [
            { name: 'pocket_residue', type: 'pocket_pdb', cardinality: 'one' },
            'bad-slot'
          ]
        },
        variants: [{ accelerator: 'cpu' }, { accelerator: 'cuda' }]
      }
    },
    created_at: '2026-08-05T00:00:00Z',
    updated_at: '2026-08-05T00:00:00Z',
    ...overrides
  }
}

test('Tool Package manifest 和 validation errors 可从当前版本安全读取', () => {
  const item = toolPackage({
    current_version: {
      ...toolPackage().current_version!,
      validation_errors: ['missing artifacts.outputs']
    }
  })

  assert.deepEqual(getToolPackageValidationErrors(item), ['missing artifacts.outputs'])
  assert.equal(getToolPackageManifest(null), undefined)
  assert.equal(formatToolPackageManifest(item).includes('pocket_residue'), true)
})

test('Artifact 输入输出槽只保留对象型 slot', () => {
  const item = toolPackage()

  assert.deepEqual(getToolPackageArtifactSlots(item, 'inputs'), [
    { name: 'protein', type: 'pdb' }
  ])
  assert.deepEqual(getToolPackageArtifactSlots(item, 'outputs'), [
    { name: 'pocket_residue', type: 'pocket_pdb', cardinality: 'one' }
  ])
})

test('Tool Package 表格摘要复用 manifest artifacts 和 variants', () => {
  assert.equal(getToolPackageContractSummary(toolPackage()), '1 输入 / 2 输出')
  assert.equal(getToolPackageVariantSummary(toolPackage()), 'cpu · cuda')
  assert.equal(
    getToolPackageVariantSummary(toolPackage({ current_version: null })),
    '无 variants'
  )
  assert.equal(
    getToolPackageVariantSummary(
      toolPackage({
        current_version: {
          ...toolPackage().current_version!,
          manifest: { variants: [{ image: 'model:latest' }] }
        }
      })
    ),
    '1 variants'
  )
})

test('Tool Package validation 状态颜色保持管理页约定', () => {
  assert.equal(getToolPackageValidationColor('valid'), 'green')
  assert.equal(getToolPackageValidationColor('invalid'), 'red')
  assert.equal(getToolPackageValidationColor(undefined), 'default')
})
