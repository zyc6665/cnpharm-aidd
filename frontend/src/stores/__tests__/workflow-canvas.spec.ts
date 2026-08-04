import { describe, it, expect, beforeEach } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'
import { useWorkflowCanvasStore } from '@/stores/workflow-canvas'
import { createInitialWorkflowSession } from '@/stores/workflow-session'
import { FREE_WORKFLOW_CANVAS_PRESET } from '@/workflow/templates'

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

  it('新流程会话应默认使用自由空白画布', () => {
    const session = createInitialWorkflowSession()

    expect(session.canvasPresetId).toBe('free-canvas')
    expect(session.canvasNodes).toEqual([])
    expect(session.canvasEdges).toEqual([])
    expect(session.hasCanvasOverride).toBe(true)
    expect(FREE_WORKFLOW_CANVAS_PRESET.nodes).toEqual([])
    expect(FREE_WORKFLOW_CANVAS_PRESET.edges).toEqual([])
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

  it('addNode 应保留工具契约中的语义输入输出', () => {
    const store = useWorkflowCanvasStore()
    const node = store.addNode({
      id: 'tool-pocket',
      toolSlug: 'pocket-explorer',
      requiredInputTypes: ['protein_pdb'],
      producedOutputTypes: ['pocket_pdb'],
    })

    expect(node.requiredInputTypes).toEqual(['protein_pdb'])
    expect(node.producedOutputTypes).toEqual(['pocket_pdb'])
  })

  it('moveNode 应同步节点本体位置，保证保存和运行定义使用最新坐标', () => {
    const store = useWorkflowCanvasStore()
    store.addNode({ id: 'n1', toolSlug: 'x' })

    store.moveNode('n1', { x: 128.4, y: 64.6 })

    expect(store.canvasNodes[0]?.position).toEqual({ x: 128, y: 65 })
    expect(store.exportNodes([])[0]?.position).toEqual({ x: 128, y: 65 })
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

  it('deleteNode 删除最后一个工具节点后应保留空画布覆盖状态', () => {
    const store = useWorkflowCanvasStore()
    store.addNode({ id: 'n1', toolSlug: 'x' })

    store.deleteNode('n1')

    expect(store.canvasNodes).toEqual([])
    expect(store.hasCanvasOverride).toBe(true)
    expect(store.exportNodes([{ id: 'fallback', type: 'tool', titleKey: 'fallback', position: { x: 0, y: 0 } }])).toEqual([])
    expect(store.exportEdges([{ id: 'edge-fallback', source: 'fallback', target: 'fallback' }])).toEqual([])
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

  it('连线变更不应覆盖工具契约语义，避免删除后依赖状态残留或丢失', () => {
    const store = useWorkflowCanvasStore()
    store.addNode({
      id: 'src',
      toolSlug: 'pocket-explorer',
      producedOutputTypes: ['pocket_pdb'],
    })
    store.addNode({
      id: 'tgt',
      toolSlug: 'docking',
      requiredInputTypes: ['protein_pdb', 'pocket_pdb'],
      producedOutputTypes: ['docking_pose'],
    })

    const edge = store.addEdge({ source: 'src', target: 'tgt', artifactType: 'pocket_pdb' })!
    expect(store.canvasNodes.find(node => node.id === 'tgt')?.requiredInputTypes).toEqual([
      'protein_pdb',
      'pocket_pdb',
    ])

    store.deleteEdge(edge.id)

    expect(store.canvasNodes.find(node => node.id === 'src')?.producedOutputTypes).toEqual(['pocket_pdb'])
    expect(store.canvasNodes.find(node => node.id === 'tgt')?.requiredInputTypes).toEqual([
      'protein_pdb',
      'pocket_pdb',
    ])
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
