import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import WorkflowResultsSidebar from './WorkflowResultsSidebar.vue'

describe('WorkflowResultsSidebar', () => {
  it('shows selected node result, workflow report, artifacts, and run history tabs', () => {
    const wrapper = mount(WorkflowResultsSidebar, {
      slots: {
        node: '<div data-testid="node-result">node</div>',
        report: '<div data-testid="workflow-report">report</div>',
        artifacts: '<div data-testid="artifacts">artifacts</div>',
        history: '<div data-testid="history">history</div>',
      },
      global: {
        stubs: {
          ATabs: { template: '<div><slot /></div>' },
          ATabPane: { props: ['tab'], template: '<section><strong>{{ tab }}</strong><slot /></section>' },
        },
      },
    })

    expect(wrapper.text()).toContain('节点结果')
    expect(wrapper.text()).toContain('结果报告')
    expect(wrapper.text()).toContain('产物')
    expect(wrapper.text()).toContain('历史')
    expect(wrapper.find('[data-testid="node-result"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="workflow-report"]').exists()).toBe(true)
  })
})
