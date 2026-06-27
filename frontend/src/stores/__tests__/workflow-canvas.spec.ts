import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useWorkflowCanvasStore } from '@/stores/workflow-canvas'

describe('useWorkflowCanvasStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
  })

  it('初始化为空画布', () => {
    const store = useWorkflowCanvasStore()
    expect(store.canvasNodes).toEqual([])
    expect(store.canvasEdges).toEqual([])
    expect(store.activeNodeId).toBeNull()
  })

  it('addNode 应添加节点并设为 active', () => {
    const store = useWorkflowCanvasStore()
    const node = store.addNode({
      id: 'tool-test-1',
      toolSlug: 'molp',
      toolName: 'Test Tool',
    })
    expect(node.id).toBe('tool-test-1')
    expect(store.canvasNodes).toHaveLength(1)
    expect(store.activeNodeId).toBe('tool-test-1')
    expect(store.nodePositionById['tool-test-1']).toBeDefined()
  })

  it('deleteNode 应移除工具节点', () => {
    const store = useWorkflowCanvasStore()
    store.addNode({ id: 'n1', toolSlug: 'x' })
    store.addNode({ id: 'n2', toolSlug: 'y' })
    expect(store.canvasNodes).toHaveLength(2)

    store.deleteNode('n1')
    expect(store.canvasNodes).toHaveLength(1)
    expect(store.canvasNodes[0]?.id).toBe('n2')
  })

  it('deleteNode 不应删除 input 类型节点', () => {
    const store = useWorkflowCanvasStore()
    // 模拟 input 节点已在画布中
    store.$patch({
      canvasNodes: [{ id: 'input-1', type: 'input', toolSlugs: [], position: { x: 0, y: 0 } }],
    })
    store.deleteNode('input-1')
    expect(store.canvasNodes).toHaveLength(1)
  })

  it('addEdge 应在有效 source/target 间创建连线', () => {
    const store = useWorkflowCanvasStore()
    store.addNode({ id: 'src', toolSlug: 'a' })
    store.addNode({ id: 'tgt', toolSlug: 'b' })

    const edge = store.addEdge({ source: 'src', target: 'tgt' })
    expect(edge).not.toBeNull()
    expect(store.canvasEdges).toHaveLength(1)
    expect(store.canvasEdges[0]?.source).toBe('src')
  })

  it('addEdge 应拒绝自环和缺失节点', () => {
    const store = useWorkflowCanvasStore()
    store.addNode({ id: 'n1', toolSlug: 'a' })

    expect(store.addEdge({ source: 'n1', target: 'n1' })).toBeNull()
    expect(store.addEdge({ source: 'n1', target: 'missing' })).toBeNull()
    expect(store.canvasEdges).toHaveLength(0)
  })

  it('deleteEdge 应移除连线', () => {
    const store = useWorkflowCanvasStore()
    store.addNode({ id: 'a', toolSlug: 'x' })
    store.addNode({ id: 'b', toolSlug: 'y' })
    const edge = store.addEdge({ source: 'a', target: 'b' })!
    expect(store.canvasEdges).toHaveLength(1)

    store.deleteEdge(edge.id)
    expect(store.canvasEdges).toHaveLength(0)
  })

  it('reset 应清空所有状态', () => {
    const store = useWorkflowCanvasStore()
    store.addNode({ id: 'n1', toolSlug: 'x' })
    store.setActiveNode('n1')
    store.reset()
    expect(store.canvasNodes).toEqual([])
    expect(store.canvasEdges).toEqual([])
    expect(store.activeNodeId).toBeNull()
  })
})
