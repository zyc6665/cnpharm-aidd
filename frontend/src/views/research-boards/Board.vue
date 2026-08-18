<template>
  <section
    data-testid="research-board-page"
    class="board-editor-page"
    :class="{ 'is-focused': focused }"
  >
    <header class="editor-header">
      <div class="title-block">
        <a-button type="text" title="返回白板列表" @click="backToList">←</a-button>
        <div>
          <h1>{{ board?.name || '科研白板' }}</h1>
          <span>{{ saveStateLabel }}</span>
        </div>
      </div>
      <div class="editor-actions">
        <a-button title="转为工作流草稿" :disabled="!board" @click="generateDraft">转为工作流</a-button>
        <a-button type="primary" :loading="saving" @click="saveBoard(false)"><SaveOutlined /> 保存</a-button>
        <a-button
          data-testid="toggle-focus-mode"
          :title="focused ? '退出专注模式' : '进入专注模式'"
          @click="focused = !focused"
        >
          <FullscreenExitOutlined v-if="focused" />
          <ExpandOutlined v-else />
        </a-button>
      </div>
    </header>

    <a-alert
      v-if="loadError"
      type="error"
      show-icon
      message="白板加载失败"
      description="无法读取当前白板。"
    >
      <template #action><a-button size="small" @click="load">重试</a-button></template>
    </a-alert>
    <a-spin v-else :spinning="loading" class="editor-loading">
      <div v-if="board" class="editor-workspace">
        <BoardObjectPalette
          v-if="!focused"
          :has-files="files.length > 0"
          :has-images="hasImages"
          :has-tools="toolsStore.workflowToolOptions.length > 0"
          :has-artifacts="artifacts.length > 0"
          @add="addObject"
        />
        <main class="canvas-region">
          <ResearchBoardCanvas
            ref="canvasRef"
            v-model="content"
            :files="files"
            :tools="toolsStore.workflowToolOptions"
            :artifacts="artifacts"
            :object-toolbar="false"
            @select-node="selectedNodeId = $event"
          >
            <template #artifact="{ artifactId, nodeId }">
              <BoardArtifactNodeContent
                v-if="artifactById(String(artifactId || ''))"
                :artifact="artifactById(String(artifactId || ''))!"
                :node-id="String(nodeId || '')"
                :disabled="preparingProtein"
                @prepare-protein="openProteinPreparation"
              />
              <span v-else class="artifact-placeholder">{{ artifactLabel(artifactId) }}</span>
            </template>
          </ResearchBoardCanvas>
        </main>
        <ProteinPreparationPanel
          v-if="!focused && proteinPreparationTarget"
          :artifact-name="proteinPreparationTarget.artifact.name"
          :disabled="saving || loading"
          :loading="preparingProtein"
          @submit="prepareProtein"
        />
        <ExternalDatabaseImportPanel
          v-if="!focused && projectId"
          :sources="externalSources"
          :disabled="saving || loading"
          :loading="importingExternal"
          @import="importExternalDatabase"
        />
        <BoardInspector
          v-if="!focused"
          v-model:name="form.name"
          v-model:description="form.description"
          :selected-node="selectedNode"
          :save-state="saveState"
          @remove-selected="removeSelected"
        />
      </div>
    </a-spin>
  </section>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { ExpandOutlined, FullscreenExitOutlined, SaveOutlined } from '@ant-design/icons-vue'
import { getProjectArtifacts } from '@/api/artifacts'
import BoardInspector from '@/components/research-boards/BoardInspector.vue'
import BoardArtifactNodeContent from '@/components/research-boards/BoardArtifactNodeContent.vue'
import BoardObjectPalette from '@/components/research-boards/BoardObjectPalette.vue'
import ExternalDatabaseImportPanel from '@/components/research-boards/ExternalDatabaseImportPanel.vue'
import ProteinPreparationPanel from '@/components/research-boards/ProteinPreparationPanel.vue'
import ResearchBoardCanvas, {
  type BoardContent,
  type BoardNodeType,
} from '@/components/research-boards/ResearchBoardCanvas.vue'
import {
  startProteinPreparation,
  type ProteinPreparationOptions,
} from '@/api/protein-preparation'
import {
  getExternalDatabaseSources,
  importExternalDatabaseArtifact,
  type ExternalDatabaseEntityType,
  type ExternalDatabaseSource,
} from '@/api/external-databases'
import {
  createBoardWorkflowDraft,
  getResearchBoard,
  updateResearchBoard,
  type ResearchBoard,
} from '@/api/research-boards'
import { getFileList } from '@/api/files'
import type { FileInfo } from '@/types/models'
import type { TypedArtifact } from '@/types/artifacts'
import { useToolsStore } from '@/stores'

const route = useRoute()
const router = useRouter()
const toolsStore = useToolsStore()
const board = ref<ResearchBoard | null>(null)
const files = ref<FileInfo[]>([])
const artifacts = ref<TypedArtifact[]>([])
const externalSources = ref<ExternalDatabaseSource[]>([])
const content = ref<BoardContent>({ nodes: [], edges: [], viewport: { x: 0, y: 0, zoom: 1 } })
const form = reactive({ name: '', description: '' })
const canvasRef = ref<InstanceType<typeof ResearchBoardCanvas> | null>(null)
const selectedNodeId = ref<string | null>(null)
const loading = ref(false)
const loadError = ref(false)
const saving = ref(false)
const importingExternal = ref(false)
const preparingProtein = ref(false)
const hydrating = ref(false)
const focused = ref(false)
const saveState = ref<'saved' | 'dirty' | 'saving' | 'error'>('saved')
const proteinPreparationTarget = ref<{ artifact: TypedArtifact; nodeId: string } | null>(null)
let autoSaveTimer: ReturnType<typeof setTimeout> | undefined

const projectId = computed(() => typeof route.params.projectId === 'string' ? route.params.projectId : null)
const boardId = computed(() => String(route.params.boardId || ''))
const selectedNode = computed(() => content.value.nodes.find(node => node.id === selectedNodeId.value) || null)
const hasImages = computed(() => files.value.some(file => file.content_type?.startsWith('image/')))
const saveStateLabel = computed(() => ({
  saved: '已保存', dirty: '有未保存修改', saving: '正在保存', error: '保存失败',
})[saveState.value])

async function load() {
  loading.value = true
  loadError.value = false
  hydrating.value = true
  try {
    const artifactRequest = projectId.value
      ? getProjectArtifacts(projectId.value)
      : Promise.resolve({ data: { items: [] } })
    const sourceRequest = projectId.value
      ? getExternalDatabaseSources()
      : Promise.resolve({ data: { sources: [] } })
    const [boardResponse, fileResponse, artifactResponse, sourceResponse] = await Promise.all([
      getResearchBoard(boardId.value),
      getFileList({ page: 1, page_size: 100 }),
      artifactRequest,
      sourceRequest,
      toolsStore.fetchWorkflowTools(),
    ])
    board.value = boardResponse.data
    files.value = fileResponse.data.items
    artifacts.value = artifactResponse.data.items
    externalSources.value = sourceResponse.data.sources
    content.value = structuredClone(boardResponse.data.content) as unknown as BoardContent
    Object.assign(form, {
      name: boardResponse.data.name,
      description: boardResponse.data.description || '',
    })
    saveState.value = 'saved'
  } catch {
    loadError.value = true
  } finally {
    loading.value = false
    await nextTick()
    hydrating.value = false
  }
}

function scheduleAutoSave() {
  if (autoSaveTimer) clearTimeout(autoSaveTimer)
  autoSaveTimer = setTimeout(() => { void saveBoard(true) }, 1200)
}

async function saveBoard(quiet: boolean) {
  if (!board.value || saving.value) return
  if (!form.name.trim()) {
    if (!quiet) message.warning('请输入白板名称')
    return
  }
  saving.value = true
  saveState.value = 'saving'
  try {
    const response = await updateResearchBoard(board.value.id, {
      name: form.name.trim(),
      description: form.description.trim(),
      content: content.value as unknown as Record<string, unknown>,
      version: board.value.version,
    })
    board.value = response.data
    saveState.value = 'saved'
    if (!quiet) message.success('白板已保存')
  } catch (error) {
    saveState.value = 'error'
    if ((error as { response?: { status?: number } }).response?.status === 409) {
      message.error('白板已在其他会话更新，请刷新后重试')
    }
  } finally {
    saving.value = false
  }
}

function addObject(type: BoardNodeType) {
  canvasRef.value?.addNode(type)
}

function removeSelected() {
  if (!selectedNodeId.value) return
  canvasRef.value?.removeNode(selectedNodeId.value)
  selectedNodeId.value = null
}

function artifactLabel(id?: string) {
  return artifacts.value.find(item => item.id === id)?.name || '科研产物引用'
}

function artifactById(id: string) {
  return artifacts.value.find(item => item.id === id) || null
}

function openProteinPreparation(input: { artifactId: string; nodeId: string }) {
  const artifact = artifactById(input.artifactId)
  if (!artifact) return
  proteinPreparationTarget.value = { artifact, nodeId: input.nodeId }
}

function nextExternalArtifactPosition() {
  const index = content.value.nodes.length
  return {
    x: 80 + (index % 4) * 280,
    y: 80 + Math.floor(index / 4) * 220,
  }
}

async function importExternalDatabase(input: {
  source: string
  entity_type: ExternalDatabaseEntityType
  identifier: string
}) {
  if (!projectId.value || !board.value) return
  importingExternal.value = true
  try {
    await importExternalDatabaseArtifact(projectId.value, {
      ...input,
      board_id: board.value.id,
      position: nextExternalArtifactPosition(),
    })
    await load()
    message.success('外部数据库记录已导入到白板')
  } finally {
    importingExternal.value = false
  }
}

function nextProteinPreparationPosition(nodeId: string) {
  const source = content.value.nodes.find(node => node.id === nodeId)
  if (!source) return nextExternalArtifactPosition()
  return {
    x: source.position.x + 320,
    y: source.position.y,
  }
}

async function prepareProtein(options: ProteinPreparationOptions) {
  if (!board.value || !proteinPreparationTarget.value) return
  preparingProtein.value = true
  try {
    const target = proteinPreparationTarget.value
    await startProteinPreparation(board.value.id, {
      artifact_id: target.artifact.id,
      source_node_id: target.nodeId,
      position: nextProteinPreparationPosition(target.nodeId),
      preparation_profile: 'docking_v1',
      options,
      advanced_options: {},
    })
    proteinPreparationTarget.value = null
    await load()
    message.success('蛋白制备节点已创建')
  } finally {
    preparingProtein.value = false
  }
}

async function generateDraft() {
  if (!board.value) return
  await saveBoard(true)
  const draft = await createBoardWorkflowDraft(board.value.id)
  sessionStorage.setItem('research-board-workflow-draft', JSON.stringify(draft.data))
  await router.push('/workflow')
}

function backToList() {
  void router.push(projectId.value ? `/projects/${projectId.value}/boards` : '/research-boards')
}

function handleBeforeUnload(event: BeforeUnloadEvent) {
  if (saveState.value !== 'dirty') return
  event.preventDefault()
  event.returnValue = ''
}

watch([content, () => form.name, () => form.description], () => {
  if (hydrating.value || !board.value) return
  saveState.value = 'dirty'
  scheduleAutoSave()
}, { deep: true })

onMounted(() => {
  window.addEventListener('beforeunload', handleBeforeUnload)
  void load()
})
onBeforeUnmount(() => {
  if (autoSaveTimer) clearTimeout(autoSaveTimer)
  window.removeEventListener('beforeunload', handleBeforeUnload)
})
</script>

<style scoped lang="less">
@import '@/assets/styles/variables.less';
.board-editor-page { height: 100vh; min-height: 640px; display: grid; grid-template-rows: 56px minmax(0, 1fr); overflow: hidden; background: @bg-body; }
.editor-header { display: flex; align-items: center; justify-content: space-between; gap: @spacing-md; padding: 0 @spacing-md; border-bottom: 1px solid @border-color; background: @bg-surface; }
.title-block, .editor-actions { display: flex; align-items: center; gap: @spacing-sm; min-width: 0; }
.title-block h1 { max-width: 50vw; margin: 0; overflow: hidden; color: @text-primary; font-size: @font-size-md; text-overflow: ellipsis; white-space: nowrap; }
.title-block span { display: block; color: @text-tertiary; font-size: @font-size-xs; }
.editor-loading { min-height: 0; }
.editor-loading :deep(.ant-spin-container) { height: 100%; }
.editor-workspace { height: 100%; min-height: 0; display: flex; }
.canvas-region { flex: 1; min-width: 0; min-height: 0; padding: @spacing-sm; }
.canvas-region :deep(.board-canvas) { height: 100%; border-radius: 0; }
.canvas-region :deep(.board-viewport) { height: calc(100% - 49px); }
.artifact-placeholder { color: @text-secondary; }
.is-focused .canvas-region { padding: 0; }
@media (max-width: 900px) { .board-inspector { display: none; } .editor-actions > :first-child { display: none; } }
</style>
