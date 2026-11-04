import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import i18n from '@/locales'

vi.mock('@/api/design', () => ({ listDesignProjects: vi.fn() }))
vi.mock('@/api/decisions', () => ({ getProjectStage: vi.fn() }))

let routeQuery: Record<string, string | undefined> = {}
vi.mock('vue-router', () => ({
  useRoute: () => ({ query: routeQuery }),
  useRouter: () => ({ push: vi.fn() }),
}))
vi.mock('@/views/workflow/GuidedWorkflow.vue', () => ({
  default: { name: 'GuidedWorkflow', props: ['projectId', 'initialStep'], template: '<div data-testid="guided-stub" />' },
}))

import { listDesignProjects } from '@/api/design'
import { getProjectStage } from '@/api/decisions'
import Pipeline from './Pipeline.vue'

// AppPageHeader exposes a named `actions` slot (not `extra`).
const stubs = {
  AppPageHeader: { template: '<div><slot name="actions" /></div>' },
}

function mockStage() {
  vi.mocked(listDesignProjects).mockResolvedValue([{ id: 'p1', name: 'P1' }] as never)
  vi.mocked(getProjectStage).mockResolvedValue({
    data: {
      currentStage: 'S1',
      stageName: '靶点确立',
      reachedStages: ['S0', 'S1'],
      nextStage: 'S2',
      counters: {
        targets: 1, structures: 0, selected_pockets: 0, candidates: 0, submitted_tasks: 0, finished_tasks: 0, decisions: 0,
      },
      gaps: [{ code: 'NO_STRUCTURE', message: 'x', action: '预测结构', link: '/projects/p1/targets' }],
    },
  } as never)
}

describe('Pipeline', () => {
  beforeEach(() => {
    routeQuery = { project_id: 'p1' }
    mockStage()
  })

  it('renders five stage cards', async () => {
    const w = mount(Pipeline, { global: { plugins: [i18n], stubs } })
    await new Promise(r => setTimeout(r))
    expect(w.findAll('[data-testid="design-stage-card"]').length).toBe(5)
  })

  it('renders the project switcher and continue button in the header actions slot', async () => {
    const w = mount(Pipeline, { global: { plugins: [i18n], stubs } })
    await new Promise(r => setTimeout(r))
    expect(w.find('[data-testid="design-pipeline-project"]').exists()).toBe(true)
    expect(w.find('[data-testid="design-pipeline-continue"]').exists()).toBe(true)
  })

  it('auto-opens the guided flow when focus=pocket is present', async () => {
    routeQuery = { project_id: 'p1', focus: 'pocket' }
    const w = mount(Pipeline, { global: { plugins: [i18n], stubs } })
    await new Promise(r => setTimeout(r))
    expect(w.find('[data-testid="design-pipeline-guided"]').exists()).toBe(true)
  })
})
