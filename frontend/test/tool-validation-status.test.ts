import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { getToolValidationSummary } from '@/utils/tool-validation'

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), '..')

function readSource(relativePath: string): string {
  return readFileSync(resolve(rootDir, relativePath), 'utf8')
}

describe('工具包验证等级', () => {
  it.each([
    [{}, '已导入', 'default'],
    [{ validation_status: 'unvalidated' }, '可运行', 'blue'],
    [{ validation_status: 'validated', hardware_validated: true }, '生产已验证', 'green'],
    [
      {
        validation_status: 'adapted_pending_hardware_validation',
        accelerator: 'haiguang_dcu',
        hardware_validated: false
      },
      '海光 DCU 待硬件验收',
      'orange'
    ],
    [
      {
        validation_status: 'validated',
        accelerator: 'nvidia_cuda',
        hardware_validated: true
      },
      'NVIDIA 生产已验证',
      'green'
    ]
  ])('将迁移验证信息映射为可上线状态 %#', (config, label, color) => {
    expect(getToolValidationSummary(config)).toMatchObject({ label, color })
  })

  it('同时保留 NVIDIA 已验证与海光 DCU 待验收信息', () => {
    const summary = getToolValidationSummary({
      variants: [
        { accelerator: 'nvidia_cuda', validation_status: 'validated', hardware_validated: true },
        {
          accelerator: 'haiguang_dcu',
          validation_status: 'adapted_pending_hardware_validation',
          hardware_validated: false
        }
      ]
    })

    expect(summary.badges).toEqual([
      { label: 'NVIDIA 生产已验证', color: 'green' },
      { label: '海光 DCU 待硬件验收', color: 'orange' }
    ])
  })

  it('管理列表复用验证等级展示，且不暴露积分或支付', () => {
    const adminTools = readSource('src/views/admin/Tools.vue')
    const validation = readSource('src/utils/tool-validation.ts')

    expect(adminTools).toContain("key: 'validation'")
    expect(adminTools).toContain('getToolValidationSummary')
    expect(validation).toContain('getToolValidationSummary')
    expect(adminTools).not.toMatch(/credits|payment|积分|支付/i)
  })
})
