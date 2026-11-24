import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import type { Task } from '@/types/models'
import TaskProgressCard from './TaskProgressCard.vue'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({
    t: (key: string, params?: Record<string, unknown>) =>
      params
        ? Object.entries(params).reduce(
            (text, [name, value]) => text.replace(`{${name}}`, String(value)),
            key
          )
        : key,
  }),
}))

vi.mock('ant-design-vue', () => ({
  message: { success: vi.fn() },
  Modal: { confirm: vi.fn() },
}))

vi.mock('@/api/tasks', () => ({
  getTaskDetail: vi.fn(),
  cancelTask: vi.fn(),
}))

vi.mock('@/api/task-events', () => ({
  openTaskEventStream: vi.fn(() => ({ close: vi.fn(), available: false })),
}))

import { getTaskDetail } from '@/api/tasks'

const stubs = {
  AButton: { template: '<button type="button"><slot /></button>' },
  ATag: { template: '<span><slot /></span>' },
  AProgress: { props: ['percent'], template: '<div class="progress">{{ percent }}</div>' },
  RouterLink: { props: ['to'], template: '<a :href="to"><slot /></a>' },
}

function task(overrides: Partial<Task> = {}): Task {
  return {
    id: 'task-1',
    tool_id: 'tool-1',
    tool_slug: 'pocket2mol-pocket-ligand-generation',
    status: 'running',
    progress: 42,
    progress_message: 'Generated 42/100',
    created_at: '2026-11-24T00:00:00Z',
    ...overrides,
  }
}

describe('TaskProgressCard', () => {
  beforeEach(() => {
    vi.mocked(getTaskDetail).mockResolvedValue({ data: task() } as never)
  })

  it('展示实时状态、进度与详情入口', async () => {
    const wrapper = mount(TaskProgressCard, {
      props: { taskId: 'task-1' },
      global: { stubs },
    })
    await flushPromises()

    expect(wrapper.get('[data-testid="task-progress-card"]').attributes('data-status')).toBe('running')
    expect(wrapper.text()).toContain('tasks.statusRunning')
    expect(wrapper.text()).toContain('42')
    expect(wrapper.get('[data-testid="task-progress-detail"]').attributes('href')).toBe('/tasks/task-1')
    expect(wrapper.find('[data-testid="task-progress-results"]').exists()).toBe(false)

    wrapper.unmount()
  })

  it('项目任务详情入口指向项目内任务页', async () => {
    vi.mocked(getTaskDetail).mockResolvedValue({
      data: task({ project_id: 'proj 1' }),
    } as never)

    const wrapper = mount(TaskProgressCard, {
      props: { taskId: 'task/1' },
      global: { stubs },
    })
    await flushPromises()

    expect(wrapper.get('[data-testid="task-progress-detail"]').attributes('href')).toBe(
      '/projects/proj%201/tasks/task%2F1'
    )

    wrapper.unmount()
  })

  it('排队中显示队列位置与预计等待时间', async () => {
    vi.mocked(getTaskDetail).mockResolvedValue({
      data: task({
        status: 'queued',
        progress: 0,
        dispatch: {
          mode: 'celery',
          queue: 'gpu_queue',
          queue_position: 2,
          estimated_wait_seconds: 180,
        } as never,
      }),
    } as never)

    const wrapper = mount(TaskProgressCard, {
      props: { taskId: 'task-1' },
      global: { stubs },
    })
    await flushPromises()

    const queue = wrapper.get('[data-testid="task-progress-queue"]')
    expect(queue.text()).toContain('design.progressCard.queuePosition')
    expect(queue.text()).toContain('design.progressCard.estimatedWait')

    wrapper.unmount()
  })

  it('成功后出现结果入口并带上任务名', async () => {
    vi.mocked(getTaskDetail).mockResolvedValue({
      data: task({ status: 'success', progress: 100 }),
    } as never)

    const wrapper = mount(TaskProgressCard, {
      props: { taskId: 'task-1', taskName: '分子生成' },
      global: { stubs },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('分子生成')
    expect(wrapper.get('[data-testid="task-progress-results"]').attributes('href')).toBe('/tasks/task-1/results')

    wrapper.unmount()
  })
})
