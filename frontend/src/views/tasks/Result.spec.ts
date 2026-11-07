import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import i18n from '@/locales'

const push = vi.fn()
vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { id: 't1' } }),
  useRouter: () => ({ push }),
}))
vi.mock('@/api/tasks', () => ({ getTaskDetail: vi.fn() }))

import { getTaskDetail } from '@/api/tasks'
import Result from './Result.vue'

const stubs = {
  SkeletonList: { template: '<div data-testid="stub-skeleton" />' },
  AppInlineError: { template: '<div data-testid="stub-error" />' },
  AppPageHeader: { template: '<div><slot name="actions" /></div>' },
  TaskContextBar: { template: '<div data-testid="stub-context" />' },
  StructureTaskResult: { template: '<div data-testid="stub-structure" />' },
  PocketTaskResult: { template: '<div data-testid="stub-pocket" />' },
  GenericTaskResult: { template: '<div data-testid="stub-generic" />' },
  GenerationResults: { template: '<div data-testid="stub-generation" />' },
  PropertyPredictResult: { template: '<div data-testid="stub-predict" />' },
  ScreenResult: { template: '<div data-testid="stub-screening" />' },
  MdResult: { template: '<div data-testid="stub-md" />' },
  FreeEnergyResult: { template: '<div data-testid="stub-free-energy" />' },
  'a-card': { template: '<div><slot /></div>' },
  'a-result': {
    props: ['title', 'subTitle'],
    template: '<div class="a-result-stub"><span>{{ title }}</span><slot /><slot name="extra" /></div>',
  },
  'a-progress': { template: '<div data-testid="stub-progress" />' },
}

function mockTask(overrides: Record<string, unknown>) {
  vi.mocked(getTaskDetail).mockResolvedValue({
    data: {
      id: 't1',
      status: 'success',
      progress: 100,
      tool_slug: 'boltz2-structure-prediction',
      outputs: null,
      ...overrides,
    },
  } as never)
}

async function mountResult() {
  const wrapper = mount(Result, { global: { plugins: [i18n], stubs } })
  await new Promise(r => setTimeout(r))
  return wrapper
}

describe('task result dispatcher', () => {
  beforeEach(() => {
    push.mockReset()
  })

  it('renders the structure result view for a structure task', async () => {
    mockTask({})
    const wrapper = await mountResult()
    expect(wrapper.find('[data-testid="stub-structure"]').exists()).toBe(true)
  })

  it('renders the pocket result view for a pocket task', async () => {
    mockTask({ tool_slug: 'lvpocket-pocket-prediction' })
    const wrapper = await mountResult()
    expect(wrapper.find('[data-testid="stub-pocket"]').exists()).toBe(true)
  })

  it('falls back to the generic result view for unknown tools', async () => {
    mockTask({ tool_slug: 'some-unknown-tool' })
    const wrapper = await mountResult()
    expect(wrapper.find('[data-testid="stub-generic"]').exists()).toBe(true)
  })

  it('shows running progress instead of a result view while the task is active', async () => {
    mockTask({ status: 'running', progress: 42, tool_slug: 'boltz2-structure-prediction' })
    const wrapper = await mountResult()
    expect(wrapper.text()).toContain('任务正在运行')
    expect(wrapper.find('[data-testid="stub-structure"]').exists()).toBe(false)
  })
})
