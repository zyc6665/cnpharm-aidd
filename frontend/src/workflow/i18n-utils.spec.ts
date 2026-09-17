import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { formatWorkflowKey, resolveWorkflowLabel } from './i18n-utils'

describe('workflow i18n utils', () => {
  it('formats missing workflow keys with a safe fallback instead of throwing', () => {
    const source = readFileSync(resolve('src/workflow/i18n-utils.ts'), 'utf8')

    expect(source).not.toContain('未命名节点')
    expect(formatWorkflowKey(undefined)).toBe('Untitled Node')
    expect(formatWorkflowKey(undefined, '未命名节点')).toBe('未命名节点')
    expect(resolveWorkflowLabel(undefined, key => key, () => false, '未命名节点')).toBe('未命名节点')
  })
})
