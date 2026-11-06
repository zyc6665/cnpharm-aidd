import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import i18n from '@/locales'
import TaskContextBar from './TaskContextBar.vue'
import { MOLECULE_GENERATION_TOOL_SLUG, POCKET_PREDICT_TOOL_SLUG } from '@/types/design'

const push = vi.hoisted(() => vi.fn())

vi.mock('vue-router', () => ({
  useRouter: () => ({ push })
}))

vi.mock('@/api/tasks', () => ({
  getTaskDetail: vi.fn()
}))

const stubs = {
  RouterLink: { template: '<a><slot /></a>' }
}

function mountBar(props: Record<string, unknown>) {
  return mount(TaskContextBar, {
    props: props as never,
    global: {
      plugins: [i18n],
      stubs
    }
  })
}

describe('TaskContextBar', () => {
  beforeEach(() => {
    push.mockReset()
  })

  it('shows the result switch for a task with a dedicated result page', () => {
    const wrapper = mountBar({
      taskId: 't1',
      active: 'detail',
      task: {
        id: 't1',
        name: '分子生成',
        status: 'success',
        tool_slug: MOLECULE_GENERATION_TOOL_SLUG
      }
    })

    expect(wrapper.find('[data-testid="task-context-result"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="task-context-back"]').exists()).toBe(true)
  })

  it('hides the result switch for structure and pocket tasks', () => {
    const wrapper = mountBar({
      taskId: 't2',
      active: 'detail',
      task: {
        id: 't2',
        name: '口袋预测',
        status: 'success',
        tool_slug: POCKET_PREDICT_TOOL_SLUG
      }
    })

    expect(wrapper.find('[data-testid="task-context-result"]').exists()).toBe(false)
  })

  it('navigates to the dedicated result page when switching views', async () => {
    const wrapper = mountBar({
      taskId: 't3',
      active: 'detail',
      task: {
        id: 't3',
        name: '分子生成',
        status: 'success',
        tool_slug: MOLECULE_GENERATION_TOOL_SLUG
      }
    })

    await wrapper.find('[data-testid="task-context-result"]').trigger('click')
    expect(push).toHaveBeenCalledWith('/tasks/t3/results')
  })
})
