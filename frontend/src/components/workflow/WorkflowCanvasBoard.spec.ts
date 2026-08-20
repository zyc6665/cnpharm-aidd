import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import i18n from '@/locales'
import WorkflowCanvasBoard from './WorkflowCanvasBoard.vue'
import type { WorkflowCanvasPreset } from '@/workflow/canvas-types'

const canvasPreset: WorkflowCanvasPreset = {
  id: 'free-canvas',
  kind: 'free',
  nameKey: 'workflow.canvas.freeFlowName',
  nodes: [
    {
      id: 'source',
      type: 'tool',
      titleKey: 'Pocket',
      position: { x: 40, y: 80 },
      producedOutputTypes: ['pocket_pdb'],
    },
    {
      id: 'target',
      type: 'tool',
      titleKey: 'Docking',
      position: { x: 320, y: 80 },
      requiredInputTypes: ['pocket_pdb'],
    },
  ],
  edges: [],
}

describe('WorkflowCanvasBoard', () => {
  it('拖动节点端口到目标节点时应发出语义连线事件', async () => {
    const wrapper = mount(WorkflowCanvasBoard, {
      props: { preset: canvasPreset },
      global: {
        plugins: [i18n],
        stubs: {
          AButton: {
            emits: ['click'],
            template: '<button @click="$emit(\'click\')"><slot /></button>',
          },
          ASpace: { template: '<div><slot /></div>' },
          ATag: { template: '<span><slot /></span>' },
          ZoomInOutlined: true,
          ZoomOutOutlined: true,
        },
      },
    })

    await wrapper.find('[data-node-port="source-output"]').trigger('pointerdown')
    await wrapper.find('[data-node-port="target-input"]').trigger('pointerup')

    expect(wrapper.emitted('add-edge')?.[0]).toEqual([
      {
        source: 'source',
        target: 'target',
        artifactType: 'pocket_pdb',
      },
    ])
  })

  it('点击连线删除控件时应发出删除连线事件', async () => {
    const wrapper = mount(WorkflowCanvasBoard, {
      props: {
        preset: {
          ...canvasPreset,
          edges: [{ id: 'edge-source-target', source: 'source', target: 'target', artifactType: 'pocket_pdb' }],
        },
      },
      global: {
        plugins: [i18n],
        stubs: {
          AButton: {
            emits: ['click'],
            template: '<button @click="$emit(\'click\')"><slot /></button>',
          },
          ASpace: { template: '<div><slot /></div>' },
          ATag: { template: '<span><slot /></span>' },
          ZoomInOutlined: true,
          ZoomOutOutlined: true,
        },
      },
    })

    await wrapper.find('[data-edge-delete="edge-source-target"]').trigger('click')

    expect(wrapper.emitted('delete-edge')?.[0]).toEqual(['edge-source-target'])
  })


  it('工具拖放到画布时应按落点创建节点', async () => {
    const wrapper = mount(WorkflowCanvasBoard, {
      props: { preset: { ...canvasPreset, nodes: [], edges: [] } },
      global: {
        plugins: [i18n],
        stubs: {
          AButton: {
            emits: ['click'],
            template: '<button @click="$emit(\'click\')"><slot /></button>',
          },
          ASpace: { template: '<div><slot /></div>' },
          ATag: { template: '<span><slot /></span>' },
          ZoomInOutlined: true,
          ZoomOutOutlined: true,
        },
      },
    })
    const surface = wrapper.find('.canvas-surface').element as HTMLElement
    surface.getBoundingClientRect = () => ({
      left: 100,
      top: 50,
      width: 600,
      height: 400,
      right: 700,
      bottom: 450,
      x: 100,
      y: 50,
      toJSON: () => ({}),
    })

    await wrapper.find('.canvas-viewport').trigger('drop', {
      clientX: 260,
      clientY: 170,
      dataTransfer: { getData: (type: string) => type === 'application/x-workflow-tool' ? 'pocket-explorer' : '' },
    })

    expect(wrapper.emitted('add-tool-node')?.[0]).toEqual([{ toolSlug: 'pocket-explorer', position: { x: 160, y: 120 } }])
  })

  it('画布视口尺寸不应跟随远端节点坐标扩展', () => {
    const wrapper = mount(WorkflowCanvasBoard, {
      props: {
        preset: {
          ...canvasPreset,
          nodes: [
            { ...canvasPreset.nodes[0]!, position: { x: 40, y: 80 } },
            { ...canvasPreset.nodes[1]!, position: { x: 6000, y: 4000 } },
          ],
        },
      },
      global: {
        plugins: [i18n],
        stubs: {
          AButton: {
            emits: ['click'],
            template: '<button @click="$emit(\'click\')"><slot /></button>',
          },
          ASpace: { template: '<div><slot /></div>' },
          ATag: { template: '<span><slot /></span>' },
          ZoomInOutlined: true,
          ZoomOutOutlined: true,
        },
      },
    })

    expect(wrapper.find('.canvas-stage').attributes('style')).toContain('width: 6476px')
    expect(wrapper.find('.workflow-canvas-board').attributes('style')).toContain('width: 100%')
    expect(wrapper.find('.workflow-canvas-board').attributes('style')).toContain('flex: 1 1 auto')
  })

})
