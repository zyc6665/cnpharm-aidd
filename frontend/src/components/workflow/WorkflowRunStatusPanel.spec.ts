import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import i18n from '@/locales'
import WorkflowRunStatusPanel from './WorkflowRunStatusPanel.vue'

const stubs = {
  AButton: {
    props: ['disabled', 'loading'],
    emits: ['click'],
    template: '<button :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
  },
  AProgress: { props: ['percent', 'status'], template: '<div class="progress" />' },
  ATag: { props: ['color'], template: '<span class="tag"><slot /></span>' },
  RedoOutlined: true,
  StopOutlined: true,
  SyncOutlined: true,
  RouterLink: {
    props: ['to'],
    template: '<a :href="to"><slot /></a>',
  },
}

function mountPanel() {
  return mount(WorkflowRunStatusPanel, {
    props: {
      run: {
        id: 'run-1',
        owner_id: 'user-1',
        workflow_definition_id: 'workflow-1',
        name: 'Failure Run',
        status: 'failure',
        definition: { nodes: [], edges: [] },
        input_files: {},
        execution_order: ['predict-pocket'],
        node_states: {
          'predict-pocket': {
            status: 'failure',
            tool_slug: 'lvpocket-pocket-prediction',
            task_id: 'task-failed-pocket',
            error_message: 'Pocket prediction failed',
          },
        },
        artifact_lineage: {},
        created_at: '2026-09-07T00:00:00Z',
        updated_at: '2026-09-07T00:01:00Z',
      } as never,
    },
    global: {
      plugins: [i18n],
      stubs,
    },
  })
}

describe('WorkflowRunStatusPanel', () => {
  it('为带任务 ID 的失败节点提供任务详情入口', () => {
    const wrapper = mountPanel()

    const taskLink = wrapper.find('.task-detail-link')
    expect(taskLink.exists()).toBe(true)
    expect(taskLink.attributes('href')).toBe('/tasks/task-failed-pocket')
    expect(taskLink.text()).toContain('task-failed-pocket')
  })

  it('为运行节点提供按 workflow/node 过滤的任务列表入口', () => {
    const wrapper = mountPanel()

    const listLink = wrapper.find('.node-task-list-link')
    expect(listLink.exists()).toBe(true)
    expect(listLink.attributes('href')).toBe(
      '/tasks?workflow_run_id=run-1&workflow_definition_id=workflow-1&workflow_node_id=predict-pocket&view=needs_attention'
    )
  })
})
