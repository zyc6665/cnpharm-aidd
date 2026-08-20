import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import WorkflowWorkbenchShell from './WorkflowWorkbenchShell.vue'

describe('WorkflowWorkbenchShell', () => {
  it('renders full workbench regions and keeps canvas as the primary area', () => {
    const wrapper = mount(WorkflowWorkbenchShell, {
      props: {
        workflowName: 'Docking Flow',
        readyCount: 1,
        runningCount: 0,
        completedCount: 0,
        failedCount: 0,
        leftWidth: 320,
        rightWidth: 380,
        leftCollapsed: false,
        rightCollapsed: false,
      },
      slots: {
        left: '<div data-testid="tool-library">tools</div>',
        canvas: '<div data-testid="canvas-region">canvas</div>',
        right: '<div data-testid="results-center">results</div>',
      },
      global: {
        stubs: {
          AButton: { template: '<button><slot /></button>' },
          ATag: { template: '<span><slot /></span>' },
          ASpace: { template: '<div><slot /></div>' },
        },
      },
    })

    expect(wrapper.find('[data-testid="workflow-workbench"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="tool-library"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="canvas-region"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="results-center"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('Docking Flow')
  })
})
