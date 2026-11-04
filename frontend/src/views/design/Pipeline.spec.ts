import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import i18n from '@/locales'

vi.mock('@/api/design', () => ({ listDesignProjects: vi.fn() }))
vi.mock('@/api/decisions', () => ({ getProjectStage: vi.fn() }))
vi.mock('vue-router', () => ({
  useRoute: () => ({ query: { project_id: 'p1' } }),
  useRouter: () => ({ push: vi.fn() }),
}))
vi.mock('@/views/workflow/GuidedWorkflow.vue', () => ({
  default: { name: 'GuidedWorkflow', template: '<div data-testid="guided-stub" />' },
}))

import { listDesignProjects } from '@/api/design'
import { getProjectStage } from '@/api/decisions'
import Pipeline from './Pipeline.vue'

const stubs = {
  AppPageHeader: { template: '<div><slot name="extra" /></div>' },
}

describe('Pipeline', () => {
  beforeEach(() => {
    vi.mocked(listDesignProjects).mockResolvedValue([{ id: 'p1', name: 'P1' }] as never)
    vi.mocked(getProjectStage).mockResolvedValue({
      data: {
        currentStage: 'S1',
        stageName: '靶点确立',
        reachedStages: ['S0', 'S1'],
        nextStage: 'S2',
        counters: {
          targets: 1,
          structures: 0,
          selected_pockets: 0,
          candidates: 0,
          submitted_tasks: 0,
          finished_tasks: 0,
          decisions: 0,
        },
        gaps: [{ code: 'NO_STRUCTURE', message: 'x', action: '预测结构', link: '/projects/p1/targets' }],
      },
    } as never)
  })

  it('renders five stage cards', async () => {
    const w = mount(Pipeline, { global: { plugins: [i18n], stubs } })
    await new Promise(r => setTimeout(r))
    expect(w.findAll('[data-testid="design-stage-card"]').length).toBe(5)
  })
})
