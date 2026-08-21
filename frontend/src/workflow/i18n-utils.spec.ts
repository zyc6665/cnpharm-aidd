import { describe, expect, it } from 'vitest'
import { formatWorkflowKey, resolveWorkflowLabel } from './i18n-utils'

describe('workflow i18n utils', () => {
  it('formats missing workflow keys with a safe fallback instead of throwing', () => {
    expect(formatWorkflowKey(undefined)).toBe('未命名节点')
    expect(resolveWorkflowLabel(undefined, key => key, () => false)).toBe('未命名节点')
  })
})
