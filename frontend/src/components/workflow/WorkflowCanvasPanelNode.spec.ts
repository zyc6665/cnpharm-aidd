import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import WorkflowCanvasPanelNode from './WorkflowCanvasPanelNode.vue'

describe('WorkflowCanvasPanelNode', () => {
  it('renders a large node panel with status, run action, and preview slot', async () => {
    const wrapper = mount(WorkflowCanvasPanelNode, {
      props: {
        node: {
          id: 'fetch-pdb-node',
          type: 'tool',
          titleKey: 'Fetch PDB',
          position: { x: 40, y: 80 },
          producedOutputTypes: ['protein_structure@1'],
        },
        title: 'Fetch PDB',
        status: 'ready',
        selected: true,
        scale: 1,
      },
      slots: { preview: '<div data-testid="node-preview">PDB preview</div>' },
      global: {
        stubs: {
          WorkflowNodeStatusBadge: { template: '<span data-testid="node-status" />' },
        },
      },
    })

    expect(wrapper.classes()).toContain('workflow-canvas-panel-node')
    expect(wrapper.text()).toContain('Fetch PDB')
    expect(wrapper.find('[data-testid="node-preview"]').exists()).toBe(true)
    expect(wrapper.find('.panel-node-title-group h3').exists()).toBe(true)

    await wrapper.find('[data-testid="run-node-button"]').trigger('click')
    expect(wrapper.emitted('run-node')).toEqual([['fetch-pdb-node']])
  })
})
