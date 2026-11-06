import { describe, it, expect } from 'vitest'
import {
  DESIGN_RUN_CATEGORIES,
  ALL_DESIGN_TOOL_SLUGS,
  findDesignRunCategory,
  resolveDesignRunPath,
  resolveTaskResultPath,
} from './runs'
import {
  MOLECULE_GENERATION_TOOL_SLUG,
  STRUCTURE_PREDICT_TOOL_SLUG,
  POCKET_PREDICT_TOOL_SLUG,
} from '@/types/design'

describe('design runs categories', () => {
  it('contains structure and pocket as first two categories', () => {
    expect(DESIGN_RUN_CATEGORIES.slice(0, 2).map(c => c.key)).toEqual(['structure', 'pocket'])
    expect(DESIGN_RUN_CATEGORIES[0]!.slugs).toEqual([STRUCTURE_PREDICT_TOOL_SLUG])
    expect(DESIGN_RUN_CATEGORIES[1]!.slugs).toEqual([POCKET_PREDICT_TOOL_SLUG])
  })

  it('ALL_DESIGN_TOOL_SLUGS includes both and has no duplicates', () => {
    expect(ALL_DESIGN_TOOL_SLUGS).toContain(STRUCTURE_PREDICT_TOOL_SLUG)
    expect(ALL_DESIGN_TOOL_SLUGS).toContain(POCKET_PREDICT_TOOL_SLUG)
    expect(new Set(ALL_DESIGN_TOOL_SLUGS).size).toBe(ALL_DESIGN_TOOL_SLUGS.length)
  })

  it('maps a structure task to its category and task-detail path', () => {
    expect(findDesignRunCategory(STRUCTURE_PREDICT_TOOL_SLUG)?.key).toBe('structure')
    expect(resolveDesignRunPath(STRUCTURE_PREDICT_TOOL_SLUG, 't1')).toBe('/tasks/t1')
  })
})

describe('resolveTaskResultPath', () => {
  it('returns null for structure and pocket tasks without a dedicated result page', () => {
    expect(resolveTaskResultPath(STRUCTURE_PREDICT_TOOL_SLUG, 't1')).toBeNull()
    expect(resolveTaskResultPath(POCKET_PREDICT_TOOL_SLUG, 't2')).toBeNull()
  })

  it('returns the dedicated path for tasks that have one', () => {
    expect(resolveTaskResultPath(MOLECULE_GENERATION_TOOL_SLUG, 't3')).toBe('/tasks/t3/results')
  })

  it('returns null for unknown or missing tool slugs', () => {
    expect(resolveTaskResultPath('unknown-tool', 't4')).toBeNull()
    expect(resolveTaskResultPath(undefined, 't5')).toBeNull()
  })
})
