import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { defineComponent, ref } from 'vue'
import Detail from './Detail.vue'

const mocks = vi.hoisted(() => {
  const state: { task: Record<string, unknown> | null } = { task: null }
  return {
    state,
    tasksStore: {
      get currentTask() {
        return state.task
      },
      detailLoading: false,
      fetchTaskDetail: vi.fn().mockResolvedValue(undefined),
      updateTaskProgress: vi.fn(),
      clearCurrentTask: vi.fn(),
      cancelTask: vi.fn(),
      retryTask: vi.fn(),
      deleteTask: vi.fn()
    },
    userStore: { isAdmin: false },
    router: { push: vi.fn(), replace: vi.fn() }
  }
})

vi.mock('@/stores', () => ({
  useTasksStore: () => mocks.tasksStore,
  useUserStore: () => mocks.userStore
}))

vi.mock('@/composables/useTaskDetailLiveUpdates', () => ({
  useTaskDetailLiveUpdates: () => ({
    logs: ref([]),
    logsTotal: ref(0),
    logsLoading: ref(false),
    fetchLogs: vi.fn(),
    start: vi.fn().mockResolvedValue(undefined),
    stop: vi.fn()
  })
}))

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { id: 'task-1' } }),
  useRouter: () => mocks.router
}))

vi.mock('vue-i18n', () => ({
  useI18n: () => ({
    t: (key: string, values?: Record<string, string | number>) =>
      values ? `${key}:${Object.values(values).join('|')}` : key
  })
}))

vi.mock('ant-design-vue', () => ({
  message: { success: vi.fn(), error: vi.fn(), warning: vi.fn() },
  Modal: { confirm: vi.fn() },
  theme: { useToken: () => ({ token: ref({ colorPrimary: '#1677ff', colorSuccess: '#52c41a' }) }) }
}))

const PassthroughStub = defineComponent({
  template: '<div><slot /><slot name="action" /><slot name="extra" /><slot name="icon" /></div>'
})

const CollapseStub = defineComponent({
  template: '<div class="collapse-stub"><slot /></div>'
})

const CollapsePanelStub = defineComponent({
  props: ['header'],
  template:
    '<div class="collapse-panel-stub"><span class="collapse-header">{{ header }}</span><slot /></div>'
})

function mountDetail() {
  return mount(Detail, {
    global: {
      stubs: {
        'router-link': true,
        'a-breadcrumb': PassthroughStub,
        'a-breadcrumb-item': PassthroughStub,
        'a-button': PassthroughStub,
        'a-space': PassthroughStub,
        'a-tag': PassthroughStub,
        'a-progress': PassthroughStub,
        'a-row': PassthroughStub,
        'a-col': PassthroughStub,
        'a-timeline': PassthroughStub,
        'a-timeline-item': PassthroughStub,
        'a-alert': PassthroughStub,
        'a-collapse': CollapseStub,
        'a-collapse-panel': CollapsePanelStub,
        'a-typography-text': PassthroughStub,
        'a-result': PassthroughStub,
        AppPageHeader: true,
        AppEmptyState: true,
        ProjectWorkspaceNav: true,
        SkeletonDetail: true,
        ResultVisualizationPanel: true,
        TaskLogPreview: true,
        TaskOutputSummary: true,
        TaskParameterTable: true
      }
    }
  })
}

function makeTask(overrides: Record<string, unknown> = {}) {
  return {
    id: 'task-1',
    name: 'Molecule task',
    status: 'queued',
    created_at: '2026-01-01T08:00:00Z',
    progress: 0,
    progress_message: '',
    tool_slug: 'pocket2mol-pocket-ligand-generation',
    tool: {
      id: 'tool-1',
      name: 'Pocket2Mol',
      slug: 'pocket2mol-pocket-ligand-generation',
      version: '1.0.0',
      description: 'desc',
      run_count: 2
    },
    queue: 'gpu_queue',
    queue_position: 3,
    estimated_wait_seconds: 120,
    ...overrides
  }
}

async function mountWithTask(task: Record<string, unknown>) {
  mocks.state.task = task
  const wrapper = mountDetail()
  await flushPromises()
  return wrapper
}

describe('TaskDetail dispatch status card', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.state.task = null
  })

  it('renders one status card without duplicating queue position when wait, queue and reservation coexist', async () => {
    const wrapper = await mountWithTask(
      makeTask({
        resource_wait: {
          category: 'quota',
          scope: 'user',
          dimension: 'gpu',
          retry_count: 2,
          next_attempt_at: '2026-01-01T09:00:00Z',
          reason: 'gpu_unavailable'
        },
        dispatch: {
          queue: 'gpu_queue',
          resource_reservation: {
            status: 'reserved',
            worker_id: 'worker-7',
            release_reason: 'preempted'
          }
        }
      })
    )

    expect(wrapper.findAll('[data-testid="task-dispatch-status-card"]')).toHaveLength(1)
    expect(wrapper.findAll('[data-testid="task-pending-queue"]')).toHaveLength(1)

    const text = wrapper.text()
    expect(text.split('tasks.queue.position').length - 1).toBe(1)
    expect(text.split('tasks.queue.estimatedWait').length - 1).toBe(1)

    expect(wrapper.get('[data-testid="task-dispatch-state"]').text()).toContain(
      'tasks.resourceWait.quotaExceeded'
    )
    expect(wrapper.get('[data-testid="task-dispatch-next-step"]').text()).toBe(
      'tasks.dispatchCard.nextStepWaitResource'
    )

    const techDetails = wrapper.get('[data-testid="task-dispatch-tech-details"]')
    expect(techDetails.text()).toContain('tasks.dispatchCard.techDetails')
    expect(techDetails.text()).toContain('worker-7')
    expect(techDetails.text()).toContain('preempted')
    expect(techDetails.text()).toContain('tasks.queue.queue:gpu_queue')
    expect(techDetails.text()).toContain('tasks.resourceWait.retryCount:2')

    wrapper.unmount()
  })

  it.each([
    {
      name: 'resource wait',
      task: makeTask({
        status: 'queued',
        resource_wait: { category: 'scheduler', retry_count: 1 }
      }),
      expected: 'tasks.dispatchCard.nextStepWaitResource'
    },
    {
      name: 'queued without resource wait',
      task: makeTask({ status: 'queued' }),
      expected: 'tasks.dispatchCard.nextStepQueued'
    },
    {
      name: 'reserved',
      task: makeTask({
        status: 'running',
        dispatch: { queue: 'gpu_queue', resource_reservation: { status: 'reserved', worker_id: 'worker-7' } }
      }),
      expected: 'tasks.dispatchCard.nextStepReserved'
    },
    {
      name: 'active',
      task: makeTask({
        status: 'running',
        dispatch: { queue: 'gpu_queue', resource_reservation: { status: 'claimed', worker_id: 'worker-7' } }
      }),
      expected: 'tasks.dispatchCard.nextStepActive'
    },
    {
      name: 'release error',
      task: makeTask({
        status: 'running',
        dispatch: {
          queue: 'gpu_queue',
          resource_reservation: { status: 'release_failed', worker_id: 'worker-7', release_error: 'boom' }
        }
      }),
      expected: 'tasks.dispatchCard.nextStepReleaseError'
    }
  ])('adapts next-step advice for $name', async ({ task, expected }) => {
    const wrapper = await mountWithTask(task)

    expect(wrapper.get('[data-testid="task-dispatch-next-step"]').text()).toBe(expected)

    wrapper.unmount()
  })
})
