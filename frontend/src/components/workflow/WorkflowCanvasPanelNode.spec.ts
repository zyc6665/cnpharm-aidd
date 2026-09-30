import { mount } from '@vue/test-utils'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import i18n from '@/locales'
import WorkflowCanvasPanelNode from './WorkflowCanvasPanelNode.vue'

describe('WorkflowCanvasPanelNode', () => {
  it('keeps canvas panel node chrome in locale keys', () => {
    const source = readFileSync(resolve('src/components/workflow/WorkflowCanvasPanelNode.vue'), 'utf8')
    const zhSource = readFileSync(resolve('src/locales/zh-CN/index.ts'), 'utf8')
    const enSource = readFileSync(resolve('src/locales/en-US/index.ts'), 'utf8')

    for (const marker of [
      'workflow.canvasNode.connectTo',
      'workflow.canvasNode.connectFrom',
      'workflow.canvasNode.configure',
      'workflow.canvasNode.delete',
      'workflow.canvasNode.inputs',
      'workflow.canvasNode.outputs',
      'workflow.canvasNode.noIo',
      'workflow.canvasNode.previewHint',
    ]) {
      expect(source).toContain(marker)
    }

    for (const marker of ['connectTo', 'connectFrom', 'previewHint']) {
      expect(zhSource).toContain(marker)
      expect(enSource).toContain(marker)
    }

    for (const literal of ['连接到此节点', '从此节点连接', '>运行<', '暂无输入输出约束', '选择节点查看配置与结果']) {
      expect(source).not.toContain(literal)
    }
  })

  it('renders a large node panel with status, configuration action, and preview slot', async () => {
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
        plugins: [i18n],
        stubs: {
          WorkflowNodeStatusBadge: { template: '<span data-testid="node-status" />' },
        },
      },
    })

    expect(wrapper.classes()).toContain('workflow-canvas-panel-node')
    expect(wrapper.text()).toContain('Fetch PDB')
    expect(wrapper.find('[data-testid="node-preview"]').exists()).toBe(true)
    expect(wrapper.find('.panel-node-title-group h3').exists()).toBe(true)

    await wrapper.find('[data-testid="configure-node-button"]').trigger('click')
    expect(wrapper.emitted('configure-node')).toEqual([['fetch-pdb-node']])
  })
})
