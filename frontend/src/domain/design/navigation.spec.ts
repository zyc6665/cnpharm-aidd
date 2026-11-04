import { describe, it, expect } from 'vitest'
import { buildDesignNavGroups, isDesignNavItemActive } from './navigation'

describe('buildDesignNavGroups', () => {
  it('groups stages in pipeline order and ends with design runs', () => {
    const groups = buildDesignNavGroups()
    expect(groups.map(g => g.groupKey)).toEqual(['prepare', 'design', 'evaluate', 'record'])
    expect(groups[0]!.items.map(i => i.key)).toEqual(['structurePredict', 'pocketPredict'])
    const last = groups[groups.length - 1]!
    expect(last.items.map(i => i.key)).toEqual(['designRuns'])
  })
})

describe('isDesignNavItemActive', () => {
  const structureItem = buildDesignNavGroups()[0]!.items[0]!
  const moleculeItem = buildDesignNavGroups()[1]!.items[0]!

  it('matches a query-bearing item by path and focus', () => {
    expect(isDesignNavItemActive(structureItem, { path: '/design', focus: 'structure' })).toBe(true)
    expect(isDesignNavItemActive(structureItem, { path: '/design', focus: 'pocket' })).toBe(false)
  })

  it('matches a plain path item', () => {
    expect(isDesignNavItemActive(moleculeItem, { path: '/design/molecules' })).toBe(true)
    expect(isDesignNavItemActive(moleculeItem, { path: '/design' })).toBe(false)
  })
})
