import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import TaskListCard from './TaskListCard.vue'
import type { Task } from '@/types/models'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (key: string) => key })
}))

const stubs = {
  AButton: { template: '<button type="button"><slot /></button>' },
  AProgress: { template: '<div class="a-progress" />' },
  ASpace: { template: '<div class="a-space"><slot /></div>' },
  ATag: { template: '<span class="a-tag"><slot /></span>' },
  ATooltip: { props: ['title'], template: '<span class="a-tooltip">{{ title }}<slot /></span>' },
  APopconfirm: { template: '<span class="a-popconfirm" @click="$emit(\'confirm\')"><slot /></span>' },
  RouterLink: { props: ['to'], template: '<a class="router-link" :href="to"><slot /></a>' },
  CalendarOutlined: true,
  CheckCircleOutlined: true,
  ClockCircleOutlined: true,
  CloseCircleOutlined: true,
  DeleteOutlined: true,
  EyeOutlined: true,
  LoadingOutlined: true,
  PlayCircleOutlined: true,
  ProjectOutlined: true,
  RedoOutlined: true,
  StopOutlined: true,
  SyncOutlined: true,
  ToolOutlined: true,
}

function task(overrides: Partial<Task> = {}): Task {
  return {
    id: 'task-123456789',
    tool_id: 'tool-1',
    status: 'running',
    progress: 42,
    created_at: '2026-09-10T00:00:00Z',
    started_at: '2026-09-10T00:01:00Z',
    name: 'Docking run',
    tool: { name: 'Pocket Finder', icon: 'PF' } as Task['tool'],
    project_id: 'project-1',
    progress_message: 'Running docking',
    ...overrides,
  }
}

describe('TaskListCard', () => {
  it('renders task identity, status, progress and project lineage context', () => {
    const wrapper = mount(TaskListCard, {
      props: {
        task: task(),
        actor: {
          isAdmin: true,
          currentProjectId: 'project-1',
          projectRole: 'owner',
        },
        currentProjectId: 'project-1',
        currentProjectName: 'Ligand project',
      },
      global: { stubs },
    })

    expect(wrapper.text()).toContain('Docking run')
    expect(wrapper.text()).toContain('Pocket Finder')
    expect(wrapper.text()).toContain('tasks.statusRunning')
    expect(wrapper.text()).toContain('Running docking')
    expect(wrapper.text()).toContain('项目：Ligand project')
    expect(wrapper.get('.router-link').attributes('href')).toBe('/projects/project-1/lineage')
  })

  it('emits open from click and keyboard activation', async () => {
    const wrapper = mount(TaskListCard, {
      props: { task: task(), actor: { isAdmin: false } },
      global: { stubs },
    })

    await wrapper.get('.task-card').trigger('click')
    await wrapper.get('.task-card').trigger('keydown.enter')
    await wrapper.get('.task-card').trigger('keydown.space')

    expect(wrapper.emitted('open')).toHaveLength(3)
  })

  it('shows only enabled task actions and emits their events', async () => {
    const wrapper = mount(TaskListCard, {
      props: { task: task({ status: 'failure' }), actor: { isAdmin: true } },
      global: { stubs },
    })

    expect(wrapper.text()).toContain('tasks.retry')
    expect(wrapper.text()).toContain('tasks.delete')
    expect(wrapper.text()).not.toContain('tasks.cancel')

    await wrapper.get('[data-testid="task-list-open"]').trigger('click')
    await wrapper.get('[data-testid="task-list-retry"]').trigger('click')
    await wrapper.get('[data-testid="task-list-delete"]').trigger('click')

    expect(wrapper.emitted('open')).toHaveLength(1)
    expect(wrapper.emitted('retry')).toHaveLength(1)
    expect(wrapper.emitted('delete')).toHaveLength(1)
  })
})
