import { test } from 'vitest'
import assert from 'node:assert/strict'
import type { ToolPackage } from '@/types/tool-packages'
import { getToolPackagePublishReadiness } from './publish-readiness'

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
      manifest: {},
      manifest_digest: 'sha256:abc',
      signature: 'cosign:abc',
      is_signed: true,
      validation_status: 'valid',
      validation_errors: []
    },
    created_at: '2026-08-05T00:00:00Z',
    updated_at: '2026-08-05T00:00:00Z',
    ...overrides
  }
}

test('已发布 Tool Package readiness 显示可被运行时选择', () => {
  assert.deepEqual(getToolPackagePublishReadiness(toolPackage({ status: 'published' })), {
    type: 'success',
    message: '已发布，可被平台运行时选择'
  })
})

test('缺少版本、校验失败、缺少签名和可发布状态分别给出说明', () => {
  assert.deepEqual(getToolPackagePublishReadiness(toolPackage({ current_version: null })), {
    type: 'warning',
    message: '当前 Package 没有版本，不能发布'
  })

  assert.deepEqual(
    getToolPackagePublishReadiness(
      toolPackage({
        current_version: {
          ...toolPackage().current_version!,
          validation_status: 'invalid'
        }
      })
    ),
    {
      type: 'error',
      message: '当前版本未通过契约校验，不能发布'
    }
  )

  assert.deepEqual(
    getToolPackagePublishReadiness(
      toolPackage({
        current_version: {
          ...toolPackage().current_version!,
          signature: null,
          is_signed: false
        }
      })
    ),
    {
      type: 'warning',
      message: '当前版本缺少签名，发布前必须补签名'
    }
  )

  assert.deepEqual(getToolPackagePublishReadiness(toolPackage()), {
    type: 'info',
    message: '当前版本已签名且校验通过，可以发布'
  })
})
