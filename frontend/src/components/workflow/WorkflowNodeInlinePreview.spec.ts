import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import WorkflowNodeInlinePreview from './WorkflowNodeInlinePreview.vue'

describe('WorkflowNodeInlinePreview', () => {
  it('shows a lightweight running state while task is running', () => {
    const wrapper = mount(WorkflowNodeInlinePreview, {
      props: {
        selected: true,
        task: { id: 'task-1', status: 'running', progress: 40, output_files: [] } as never,
        artifacts: [],
      },
      global: { stubs: { AProgress: true, AEmpty: true, ResultVisualizationPanel: true } },
    })

    expect(wrapper.text()).toContain('40%')
  })

  it('lazy-renders visualization only for selected successful nodes', () => {
    const wrapper = mount(WorkflowNodeInlinePreview, {
      props: {
        selected: false,
        task: {
          id: 'task-1',
          status: 'success',
          progress: 100,
          output_files: [{ id: 'f1', filename: 'ligand.sdf', url: '/f1' }],
        } as never,
        artifacts: [],
      },
      global: {
        stubs: {
          AEmpty: true,
          ResultVisualizationPanel: { template: '<div data-testid="visualization" />' },
        },
      },
    })

    expect(wrapper.find('[data-testid="visualization"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('ligand.sdf')
  })
})
