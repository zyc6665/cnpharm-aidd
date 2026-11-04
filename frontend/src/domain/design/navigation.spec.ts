import { describe, it, expect } from 'vitest'
import { buildDesignNavGroups } from './navigation'

describe('buildDesignNavGroups', () => {
  it('groups stages in pipeline order and ends with design runs', () => {
    const groups = buildDesignNavGroups()
    expect(groups.map(g => g.groupKey)).toEqual(['prepare', 'design', 'evaluate', 'record'])
    expect(groups[0]!.items.map(i => i.key)).toEqual(['structurePredict', 'pocketPredict'])
    const last = groups[groups.length - 1]!
    expect(last.items.map(i => i.key)).toEqual(['designRuns'])
  })
})
