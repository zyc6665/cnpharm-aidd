import { describe, it, expect } from 'vitest'
import { buildDesignStages, firstMissingStage, DESIGN_STAGES } from './pipeline'
import type { ProjectStage } from '@/types/decisions'

const stage: ProjectStage = {
  currentStage: 'S2',
  stageName: '结构与口袋就绪',
  reachedStages: ['S0', 'S1', 'S2'],
  nextStage: 'S3',
  counters: {
    targets: 1,
    structures: 2,
    selected_pockets: 0,
    candidates: 0,
    submitted_tasks: 0,
    finished_tasks: 0,
    decisions: 0,
  },
  gaps: [
    { code: 'NO_POCKET_SELECTED', message: '未选定口袋', action: '选定口袋', link: '/projects/p1/targets' },
  ],
}

describe('buildDesignStages', () => {
  it('exposes five ordered stages', () => {
    expect(DESIGN_STAGES.map(s => s.key)).toEqual([
      'structure',
      'pocket',
      'molecule',
      'evaluation',
      'validation',
    ])
  })

  it('marks readiness from counters and picks gap link as primaryPath', () => {
    const states = buildDesignStages(stage, 'p1')
    expect(states[0]).toMatchObject({ key: 'structure', readiness: 'ready', count: 2 })
    expect(states[1]).toMatchObject({
      key: 'pocket',
      readiness: 'missing',
      count: 0,
      primaryPath: '/projects/p1/targets',
    })
    expect(states[2]!.primaryPath).toBe('/design/molecules?project_id=p1')
  })

  it('returns all empty when stage is null', () => {
    expect(buildDesignStages(null, 'p1').every(s => s.readiness === 'empty')).toBe(true)
  })

  it('firstMissingStage returns the first non-ready stage', () => {
    expect(firstMissingStage(buildDesignStages(stage, 'p1'))?.key).toBe('pocket')
  })
})
