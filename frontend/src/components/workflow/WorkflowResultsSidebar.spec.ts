import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import i18n from '@/locales'
import WorkflowResultsSidebar from './WorkflowResultsSidebar.vue'

describe('WorkflowResultsSidebar', () => {
  it('keeps tab labels in locale keys', () => {
    const source = readFileSync(resolve('src/components/workflow/WorkflowResultsSidebar.vue'), 'utf8')

    for (const marker of [
      'useI18n',
      'workflow.resultsSidebar.tabs.node',
      'workflow.resultsSidebar.tabs.inputs',
      'workflow.resultsSidebar.tabs.preflight',
      'workflow.resultsSidebar.tabs.report',
      'workflow.resultsSidebar.tabs.artifacts',
      'workflow.resultsSidebar.tabs.history',
    ]) {
      expect(source).toContain(marker)
    }

    for (const literal of ['节点结果', '运行配置', '预检', '结果报告', '产物', '历史']) {
      expect(source).not.toContain(`tab="${literal}"`)
    }
  })

  it('shows selected node result, workflow report, artifacts, and run history tabs', () => {
    const wrapper = mount(WorkflowResultsSidebar, {
      slots: {
        node: '<div data-testid="node-result">node</div>',
        report: '<div data-testid="workflow-report">report</div>',
        artifacts: '<div data-testid="artifacts">artifacts</div>',
        history: '<div data-testid="history">history</div>',
      },
      global: {
        plugins: [i18n],
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
