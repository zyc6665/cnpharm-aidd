<template>
  <div class="board-canvas" data-testid="board-canvas">
    <div class="board-toolbar">
      <a-space v-if="objectToolbar" wrap>
        <a-button size="small" @click="addNode('note')">便笺</a-button>
        <a-button size="small" :disabled="!files.length" @click="addNode('file')">文件</a-button>
        <a-button size="small" :disabled="!imageOptions.length" @click="addNode('image')">图片</a-button>
        <a-button size="small" :disabled="!tools.length" @click="addNode('tool')">工具</a-button>
        <a-button size="small" :type="connectSourceId !== null ? 'primary' : 'default'" :disabled="content.nodes.length < 2" @click="toggleConnect">
          <LinkOutlined /> {{ connectSourceId !== null ? '选择节点' : '连接节点' }}
        </a-button>
      </a-space>
      <a-space size="small">
        <a-button size="small" title="撤销" :disabled="!undoStack.length" @click="undo"><UndoOutlined /></a-button>
        <a-button size="small" title="重做" :disabled="!redoStack.length" @click="redo"><RedoOutlined /></a-button>
        <a-button size="small" title="缩小" @click="changeZoom(zoom - 0.1)"><ZoomOutOutlined /></a-button>
        <span class="zoom-value">{{ Math.round(zoom * 100) }}%</span>
        <a-button size="small" title="放大" @click="changeZoom(zoom + 0.1)"><ZoomInOutlined /></a-button>
        <a-button size="small" @click="changeZoom(1)">复位</a-button>
      </a-space>
    </div>

    <div
      ref="viewportRef"
      class="board-viewport"
      @pointerdown.self="startPan"
      @wheel.ctrl.prevent="changeZoom(zoom - $event.deltaY * 0.001)"
    >
      <div data-testid="board-stage" class="board-stage" :style="{ width: `${1600 * zoom}px`, height: `${1000 * zoom}px` }" @pointerdown.self="startPan">
        <div class="board-surface" :style="surfaceStyle" @pointerdown.self="startPan">
          <svg class="board-edges" width="1600" height="1000" aria-label="白板节点关系">
            <g v-for="edge in resolvedEdges" :key="edge.id">
              <line :x1="edge.x1" :y1="edge.y1" :x2="edge.x2" :y2="edge.y2" />
              <text :x="(edge.x1 + edge.x2) / 2" :y="(edge.y1 + edge.y2) / 2 - 8">{{ edge.label }}</text>
            </g>
          </svg>

          <article
            v-for="node in content.nodes"
            :key="node.id"
            class="board-node"
            :class="[`is-${node.type}`, { 'is-connecting': connectSourceId === node.id }]"
            :style="{ left: `${node.position.x}px`, top: `${node.position.y}px` }"
            @click.stop="selectNode(node.id)"
            @pointerdown="startDrag($event, node)"
          >
            <header>
              <strong>{{ nodeLabel(node.type) }}</strong>
              <button type="button" title="删除节点" @pointerdown.stop @click.stop="removeNode(node.id)"><DeleteOutlined /></button>
            </header>
            <a-textarea v-if="node.type === 'note'" :value="node.content" :rows="4" @pointerdown.stop @update:value="updateNode(node.id, 'content', $event)" />
            <a-select v-else-if="node.type === 'tool'" :value="node.tool_id" :options="toolOptions" show-search option-filter-prop="label" @pointerdown.stop @change="updateNode(node.id, 'tool_id', String($event))" />
            <a-select v-else-if="node.type === 'file'" :value="node.file_id" :options="fileOptions" show-search option-filter-prop="label" @pointerdown.stop @change="updateNode(node.id, 'file_id', String($event))" />
            <template v-else-if="node.type === 'image'">
              <a-select :value="node.file_id" :options="imageOptions" show-search option-filter-prop="label" @pointerdown.stop @change="updateNode(node.id, 'file_id', String($event))" />
              <img v-if="node.file_id" :src="`/api/v1/files/${node.file_id}/download`" alt="白板图片" />
            </template>
            <template v-else>
              <slot name="artifact" :artifact-id="node.artifact_id">
                <span class="artifact-reference">{{ artifactName(node.artifact_id) }}</span>
              </slot>
            </template>
          </article>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue'
import { DeleteOutlined, LinkOutlined, RedoOutlined, UndoOutlined, ZoomInOutlined, ZoomOutOutlined } from '@ant-design/icons-vue'
import { useCanvasViewport } from '@/composables/useCanvasViewport'

export type BoardNodeType = 'note' | 'file' | 'image' | 'tool' | 'artifact'
export interface BoardNode { id: string; type: BoardNodeType; position: { x: number; y: number }; content?: string; tool_id?: string; file_id?: string; artifact_id?: string }
export interface BoardEdge { id: string; source: string; target: string; label?: string }
export interface BoardContent { nodes: BoardNode[]; edges: BoardEdge[]; viewport: { x: number; y: number; zoom: number } }

const props = withDefaults(defineProps<{
  modelValue: BoardContent
  files: Array<{ id: string; filename: string; content_type?: string }>
  tools: Array<{ id: string; name: string }>
  artifacts?: Array<{ id: string; name: string }>
  objectToolbar?: boolean
}>(), { artifacts: () => [], objectToolbar: true })
const emit = defineEmits<{
  (event: 'update:modelValue', value: BoardContent): void
  (event: 'select-node', id: string): void
}>()
const viewportRef = ref<HTMLElement>()
const undoStack = ref<BoardContent[]>([])
const redoStack = ref<BoardContent[]>([])
const connectSourceId = ref<string | null>(null)
const content = computed(() => props.modelValue)
const fileOptions = computed(() => props.files.map(file => ({ value: file.id, label: file.filename })))
const imageOptions = computed(() => props.files.filter(file => file.content_type?.startsWith('image/')).map(file => ({ value: file.id, label: file.filename })))
const toolOptions = computed(() => props.tools.map(tool => ({ value: tool.id, label: tool.name })))
const artifactName = (id?: string) => props.artifacts.find(item => item.id === id)?.name || '科研产物引用'
const { zoom, setZoom, surfaceStyle } = useCanvasViewport(props.modelValue.viewport?.zoom || 1)
const nodeLabel = (type: BoardNodeType) => ({ note: '研究便笺', file: '文件', image: '图片', tool: '工具', artifact: '科研产物' })[type]

const resolvedEdges = computed(() => {
  const nodes = new Map(content.value.nodes.map(node => [node.id, node]))
  return content.value.edges.flatMap(edge => {
    const source = nodes.get(edge.source)
    const target = nodes.get(edge.target)
    if (!source || !target) return []
    return [{ ...edge, x1: source.position.x + 240, y1: source.position.y + 75, x2: target.position.x, y2: target.position.y + 75 }]
  })
})

function clone(value: BoardContent): BoardContent {
  return JSON.parse(JSON.stringify(value)) as BoardContent
}
function commit(next: BoardContent, record = true) {
  if (record) {
    undoStack.value = [...undoStack.value.slice(-49), clone(props.modelValue)]
    redoStack.value = []
  }
  emit('update:modelValue', next)
}
function commitNodes(nodes: BoardNode[], record = true) { commit({ ...props.modelValue, nodes }, record) }
function changeZoom(value: number) {
  setZoom(value)
  commit({ ...props.modelValue, viewport: { ...props.modelValue.viewport, zoom: zoom.value } })
}
function addNode(type: BoardNodeType) {
  const index = content.value.nodes.length
  const reference = type === 'tool'
      ? { tool_id: props.tools[0]?.id }
    : type === 'artifact'
      ? { artifact_id: props.artifacts[0]?.id }
    : type === 'file'
      ? { file_id: props.files[0]?.id }
      : type === 'image'
        ? { file_id: props.files.find(file => file.content_type?.startsWith('image/'))?.id }
        : { content: '' }
  if ((type === 'tool' && !reference.tool_id) || (type === 'artifact' && !reference.artifact_id) || ((type === 'file' || type === 'image') && !reference.file_id)) return
  commitNodes([...content.value.nodes, { id: `${type}-${Date.now()}`, type, position: { x: 80 + (index % 4) * 280, y: 80 + Math.floor(index / 4) * 220 }, ...reference }])
}
function removeNode(id: string) {
  commit({ ...props.modelValue, nodes: content.value.nodes.filter(node => node.id !== id), edges: content.value.edges.filter(edge => edge.source !== id && edge.target !== id) })
  if (connectSourceId.value === id) connectSourceId.value = null
}
function updateNode(id: string, key: keyof BoardNode, value: string) { commitNodes(content.value.nodes.map(node => node.id === id ? { ...node, [key]: value } : node)) }
function toggleConnect() { connectSourceId.value = connectSourceId.value ? null : '' }
function selectConnectionNode(nodeId: string) {
  if (connectSourceId.value === null) return
  if (!connectSourceId.value) { connectSourceId.value = nodeId; return }
  if (connectSourceId.value === nodeId) { connectSourceId.value = null; return }
  const exists = content.value.edges.some(edge => edge.source === connectSourceId.value && edge.target === nodeId)
  if (!exists) commit({ ...props.modelValue, edges: [...content.value.edges, { id: `edge-${Date.now()}`, source: connectSourceId.value, target: nodeId }] })
  connectSourceId.value = null
}
function selectNode(nodeId: string) {
  emit('select-node', nodeId)
  selectConnectionNode(nodeId)
}
function undo() {
  const previous = undoStack.value[undoStack.value.length - 1]
  if (!previous) return
  redoStack.value = [...redoStack.value, clone(props.modelValue)]
  undoStack.value = undoStack.value.slice(0, -1)
  emit('update:modelValue', previous)
}
function redo() {
  const next = redoStack.value[redoStack.value.length - 1]
  if (!next) return
  undoStack.value = [...undoStack.value, clone(props.modelValue)]
  redoStack.value = redoStack.value.slice(0, -1)
  emit('update:modelValue', next)
}
function startDrag(event: PointerEvent, node: BoardNode) {
  if (event.button !== 0 || (event.target as HTMLElement).closest('input,textarea,button,.ant-select')) return
  const original = clone(props.modelValue)
  const start = { x: event.clientX, y: event.clientY, position: node.position }
  const move = (next: PointerEvent) => {
    const position = { x: Math.max(0, start.position.x + (next.clientX - start.x) / zoom.value), y: Math.max(0, start.position.y + (next.clientY - start.y) / zoom.value) }
    commitNodes(content.value.nodes.map(item => item.id === node.id ? { ...item, position } : item), false)
  }
  const up = () => {
    undoStack.value = [...undoStack.value.slice(-49), original]
    redoStack.value = []
    window.removeEventListener('pointermove', move)
    window.removeEventListener('pointerup', up)
  }
  window.addEventListener('pointermove', move)
  window.addEventListener('pointerup', up)
}
function startPan(event: PointerEvent) {
  const viewport = viewportRef.value
  if (!viewport || event.button !== 0) return
  const start = { x: event.clientX, y: event.clientY, left: viewport.scrollLeft, top: viewport.scrollTop }
  const move = (next: PointerEvent) => { viewport.scrollLeft = start.left - (next.clientX - start.x); viewport.scrollTop = start.top - (next.clientY - start.y) }
  const up = () => {
    window.removeEventListener('pointermove', move)
    window.removeEventListener('pointerup', up)
    commit({ ...props.modelValue, viewport: { x: viewport.scrollLeft, y: viewport.scrollTop, zoom: zoom.value } }, false)
  }
  window.addEventListener('pointermove', move)
  window.addEventListener('pointerup', up)
}
onMounted(() => {
  void nextTick(() => {
    if (!viewportRef.value) return
    viewportRef.value.scrollLeft = props.modelValue.viewport.x || 0
    viewportRef.value.scrollTop = props.modelValue.viewport.y || 0
  })
})
defineExpose({ addNode, removeNode })
</script>

<style scoped lang="less">
@import '@/assets/styles/variables.less';
.board-canvas { overflow: hidden; border: 1px solid @border-color; border-radius: @border-radius-md; }
.board-toolbar { display: flex; align-items: center; justify-content: space-between; gap: @spacing-sm; padding: @spacing-sm; border-bottom: 1px solid @border-color; background: @bg-surface; }
.zoom-value { width: 48px; color: @text-secondary; text-align: center; }
.board-viewport { height: 560px; overflow: auto; touch-action: none; cursor: grab; background-color: @bg-body; background-image: linear-gradient(@border-color 1px, transparent 1px), linear-gradient(90deg, @border-color 1px, transparent 1px); background-size: 24px 24px; }
.board-stage { position: relative; }
.board-surface { position: absolute; width: 1600px; height: 1000px; }
.board-edges { position: absolute; inset: 0; pointer-events: none; }
.board-edges line { stroke: @accent-color; stroke-width: 2; }
.board-edges text { fill: @text-tertiary; font-size: 12px; text-anchor: middle; }
.board-node { position: absolute; width: 240px; min-height: 150px; padding: @spacing-sm; border: 1px solid @border-color; border-left: 4px solid @accent-color; background: @bg-elevated; box-shadow: @shadow-md; cursor: grab; touch-action: none; }
.board-node.is-connecting { box-shadow: 0 0 0 3px @accent-color-light, @shadow-md; }
.board-node header { display: flex; align-items: center; justify-content: space-between; margin-bottom: @spacing-sm; font-size: @font-size-sm; }
.board-node header button { border: 0; background: transparent; color: @text-tertiary; cursor: pointer; }
.board-node :deep(.ant-select) { width: 100%; }
.board-node.is-note { border-left-color: @warning-color; }
.board-node.is-file { border-left-color: @success-color; }
.board-node.is-image { border-left-color: @info-color; }
.board-node.is-artifact { border-left-color: @accent-color; }
.artifact-reference { display: block; color: @text-secondary; overflow-wrap: anywhere; }
.board-node img { display: block; max-width: 100%; max-height: 180px; margin-top: @spacing-sm; object-fit: contain; }
@media (max-width: 768px) { .board-toolbar { align-items: flex-start; flex-direction: column; } .board-viewport { height: 480px; } }
</style>
