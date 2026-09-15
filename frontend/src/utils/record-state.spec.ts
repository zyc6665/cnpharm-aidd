import { describe, expect, it } from 'vitest'
import { replaceRecord } from './record-state'

describe('record state helpers', () => {
  it('replaces a record in place and removes stale keys', () => {
    const target: Record<string, number | undefined> = {
      stale: 1,
      keep: 2,
    }

    replaceRecord(target, {
      keep: undefined,
      next: 3,
    })

    expect(target).toEqual({ keep: undefined, next: 3 })
  })
})
