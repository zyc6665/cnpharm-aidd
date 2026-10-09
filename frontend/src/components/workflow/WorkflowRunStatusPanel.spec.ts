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
        definition: {
          nodes: [
            {
              id: 'predict-pocket',
              kind: 'tool',
              titleKey: 'lvpocket-pocket-prediction',
              tool_slug: 'lvpocket-pocket-prediction',
            },
          ],
          edges: [],
        },
        input_files: {},
        execution_order: ['predict-pocket'],
        node_states: {
          'predict-pocket': {
            status: 'failure',
            tool_slug: 'lvpocket-pocket-prediction',
            task_id: 'task-failed-pocket',
            tool_version_id: 'version-internal-pocket',
            tool_version: { id: 'version-internal-pocket', version: '1.0.0' },
            input_file_ids: ['file-input-pocket'],
            params: {
              pdb_id: '1AKI',
              workflow_run_id: 'run-1',
              workflow_node_id: 'predict-pocket',
              workflow_definition_id: 'workflow-1',
              input_files: { protein_pdb: 'input/prepared.pdb' },
            },
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
  it('以可读信息展示失败节点，不暴露内部标识或原始参数', () => {
    const wrapper = mountPanel()

    const taskLink = wrapper.find('.task-detail-link')
    expect(taskLink.exists()).toBe(true)
    expect(taskLink.attributes('href')).toBe('/tasks/task-failed-pocket')
    expect(taskLink.text()).toContain('查看任务详情')
    expect(wrapper.text()).toContain('口袋预测')
    expect(wrapper.text()).toContain('1.0.0')
    expect(wrapper.text()).toContain('已绑定 1 个输入')
    expect(wrapper.text()).toContain('PDB 编号：1AKI')
    expect(wrapper.text()).not.toContain('task-failed-pocket')
    expect(wrapper.text()).not.toContain('version-internal-pocket')
    expect(wrapper.text()).not.toContain('file-input-pocket')
    expect(wrapper.text()).not.toContain('workflow_run_id')
    expect(wrapper.text()).not.toContain('input/prepared.pdb')
  })

  it('为运行节点提供不泄露内部参数的记录入口', () => {
    const wrapper = mountPanel()

    const listLink = wrapper.find('.node-task-list-link')
    expect(listLink.exists()).toBe(true)
    expect(listLink.attributes('href')).toBe(
      '/tasks?workflow_run_id=run-1&workflow_definition_id=workflow-1&workflow_node_id=predict-pocket&view=needs_attention'
    )
    expect(listLink.text()).toContain('查看节点记录')
    expect(listLink.text()).not.toContain('workflow_run_id')
  })
})
