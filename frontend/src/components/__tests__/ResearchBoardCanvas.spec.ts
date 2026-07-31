import { describe, expect, it } from 'vitest'
import { mount } from '@vue/test-utils'
import ResearchBoardCanvas, { type BoardContent } from '@/components/research-boards/ResearchBoardCanvas.vue'
import { useCanvasViewport } from '@/composables/useCanvasViewport'

const emptyContent = (): BoardContent => ({
  nodes: [],
  edges: [],
  viewport: { x: 0, y: 0, zoom: 1 },
})

const largeBoardContent = (): BoardContent => ({
  nodes: Array.from({ length: 200 }, (_, index) => ({
    id: `note-${index}`,
    type: 'note',
    position: { x: (index % 10) * 120, y: Math.floor(index / 10) * 80 },
    content: `假设 ${index}`,
  })),
  edges: [],
  viewport: { x: 0, y: 0, zoom: 1 },
})

const stubs = {
  AButton: { template: '<button v-bind="$attrs"><slot /></button>' },
  ASpace: { template: '<div><slot /></div>' },
  ATextarea: { template: '<textarea />' },
  ASelect: { template: '<select />' },
  DeleteOutlined: true,
  LinkOutlined: true,
  RedoOutlined: true,
  UndoOutlined: true,
  ZoomInOutlined: true,
  ZoomOutOutlined: true,
}

describe('ResearchBoardCanvas', () => {
  it('创建便笺节点并输出新的画布内容', async () => {
    const wrapper = mount(ResearchBoardCanvas, {
      props: { modelValue: emptyContent(), files: [], tools: [] },
      global: { stubs },
    })
    const noteButton = wrapper.findAll('button').find(button => button.text().includes('便笺'))
    await noteButton?.trigger('click')

    const emitted = wrapper.emitted('update:modelValue')
    expect(emitted).toHaveLength(1)
    const content = emitted?.[0]?.[0] as BoardContent
    expect(content.nodes).toHaveLength(1)
    expect(content.nodes[0]?.type).toBe('note')
  })

  it('没有可访问引用时禁用文件、图片和工具节点', () => {
    const wrapper = mount(ResearchBoardCanvas, {
      props: { modelValue: emptyContent(), files: [], tools: [] },
      global: { stubs },
    })
    for (const label of ['文件', '图片', '工具']) {
      const button = wrapper.findAll('button').find(item => item.text().includes(label))
      expect(button?.attributes('disabled')).toBeDefined()
    }
  })

  it('视口缩放被限制在可用范围', () => {
    const viewport = useCanvasViewport()
    viewport.setZoom(10)
    expect(viewport.zoom.value).toBe(1.6)
    viewport.setZoom(0)
    expect(viewport.zoom.value).toBe(0.5)
  })

  it('200 节点白板保持固定画布尺寸并暴露节点规模', async () => {
    const wrapper = mount(ResearchBoardCanvas, {
      props: { modelValue: largeBoardContent(), files: [], tools: [] },
      global: { stubs },
    })

    const stage = wrapper.get('[data-testid="board-stage"]')
    expect(stage.attributes('style')).toContain('width: 1600px')
    expect(stage.attributes('style')).toContain('height: 1000px')
    expect(stage.attributes('data-node-count')).toBe('200')
    expect(stage.attributes('aria-label')).toBe('科研白板画布，当前 200 个节点')

    await wrapper.findAll('.board-node')[199]?.trigger('click')
    expect(wrapper.emitted('select-node')?.[0]).toEqual(['note-199'])
  })
})
