import { describe, it, expect } from 'vitest'
import { buildDesignNavGroups, isDesignNavItemActive } from './navigation'

describe('buildDesignNavGroups', () => {
  it('groups stages in pipeline order; design runs moved into task center', () => {
    const groups = buildDesignNavGroups()
    expect(groups.map(g => g.groupKey)).toEqual(['prepare', 'design', 'evaluate'])
    expect(groups[0]!.items.map(i => i.key)).toEqual(['structurePredict', 'pocketPredict'])
    expect(groups[0]!.items.every(i => !i.isNew)).toBe(true)
    expect(groups.flatMap(g => g.items.map(i => i.key))).not.toContain('designRuns')
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
