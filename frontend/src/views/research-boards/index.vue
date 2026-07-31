<template>
  <div class="board-page">
    <AppPageHeader title="科研白板" subtitle="整理假设、文件与工具，再按需转入可执行工作流">
      <template #actions>
        <a-button type="primary" @click="createBoard"><PlusOutlined /> 新建白板</a-button>
      </template>
    </AppPageHeader>

    <a-alert
      v-if="loadError"
      class="board-load-error"
      type="error"
      show-icon
      message="科研白板加载失败"
      description="服务暂时不可用，请稍后重试。"
    >
      <template #action><a-button size="small" @click="load">重试</a-button></template>
    </a-alert>
    <a-skeleton v-else-if="loading" active :paragraph="{ rows: 6 }" />
    <a-empty v-else-if="!boards.length" description="暂无科研白板">
      <a-button type="primary" @click="createBoard">创建第一个白板</a-button>
    </a-empty>
    <div v-else class="board-grid">
      <a-card v-for="board in boards" :key="board.id" class="board-card" @click="openBoard(board)">
        <template #title>{{ board.name }}</template>
        <template #extra>
          <a-popconfirm title="确定删除这个白板？删除后无法恢复。" @confirm="removeBoard(board)">
            <a-button type="text" danger title="删除" @click.stop><DeleteOutlined /></a-button>
          </a-popconfirm>
        </template>
        <p>{{ board.description || '尚未添加研究说明' }}</p>
        <div class="board-meta"><span>{{ board.node_count }} 个节点</span><span>{{ formatDate(board.updated_at) }}</span></div>
      </a-card>
    </div>

    <a-drawer
      v-model:open="drawerOpen"
      :title="activeBoard?.name || '新建白板'"
      width="min(1120px, 100vw)"
      :mask-closable="!dirty || saveState === 'saved'"
      destroy-on-close
    >
      <a-spin :spinning="detailLoading">
        <a-form layout="vertical">
          <a-row :gutter="12">
            <a-col :xs="24" :md="10"><a-form-item label="名称" required><a-input v-model:value="form.name" :maxlength="160" /></a-form-item></a-col>
            <a-col :xs="24" :md="14"><a-form-item label="说明"><a-input v-model:value="form.description" :maxlength="2000" /></a-form-item></a-col>
          </a-row>
        </a-form>
        <ResearchBoardCanvas v-model="boardContent" :files="files" :tools="toolsStore.workflowToolOptions" />
      </a-spin>
      <template #footer>
        <div class="drawer-footer">
          <span class="save-state" :class="`is-${saveState}`">{{ saveStateLabel }}</span>
          <a-space>
            <a-button @click="drawerOpen = false">关闭</a-button>
            <a-button :disabled="!activeBoard || saving" @click="generateDraft">转为工作流草稿</a-button>
            <a-button type="primary" :loading="saving" @click="saveBoard(true)">保存并关闭</a-button>
          </a-space>
        </div>
      </template>
    </a-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import dayjs from 'dayjs'
import { message } from 'ant-design-vue'
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons-vue'
import AppPageHeader from '@/components/common/AppPageHeader.vue'
import ResearchBoardCanvas, { type BoardContent } from '@/components/research-boards/ResearchBoardCanvas.vue'
import {
  createBoardWorkflowDraft,
  createResearchBoard,
  deleteResearchBoard,
  getResearchBoard,
  getResearchBoards,
  updateResearchBoard,
  type ResearchBoard,
  type ResearchBoardSummary
} from '@/api/research-boards'
import { getFileList } from '@/api/files'
import type { FileInfo } from '@/types/models'
import { useToolsStore } from '@/stores'

const router = useRouter()
const route = useRoute()
const toolsStore = useToolsStore()
const boards = ref<ResearchBoardSummary[]>([])
const files = ref<FileInfo[]>([])
const loading = ref(false)
const loadError = ref(false)
const detailLoading = ref(false)
const saving = ref(false)
const drawerOpen = ref(false)
const dirty = ref(false)
const hydrating = ref(false)
const activeBoard = ref<ResearchBoard | null>(null)
const saveState = ref<'saved' | 'dirty' | 'saving' | 'error'>('saved')
const form = reactive({ name: '', description: '' })
const emptyContent = (): BoardContent => ({ nodes: [], edges: [], viewport: { x: 0, y: 0, zoom: 1 } })
const boardContent = ref<BoardContent>(emptyContent())
let autoSaveTimer: ReturnType<typeof setTimeout> | undefined

const saveStateLabel = computed(() => ({ saved: '已保存', dirty: '有未保存修改', saving: '正在保存…', error: '保存失败' })[saveState.value])
const formatDate = (value: string) => dayjs(value).format('YYYY-MM-DD HH:mm')

async function load() {
  loading.value = true
  loadError.value = false
  try {
    const [boardResponse, fileResponse] = await Promise.all([
      getResearchBoards(),
      getFileList({ page: 1, page_size: 100 }),
      toolsStore.fetchWorkflowTools()
    ])
    boards.value = boardResponse.data.items
    files.value = fileResponse.data.items
    const requestedBoardId = route.query.board
    if (typeof requestedBoardId === 'string') {
      const requestedBoard = boards.value.find(board => board.id === requestedBoardId)
      if (requestedBoard) await openBoard(requestedBoard)
    }
  } catch {
    loadError.value = true
  } finally {
    loading.value = false
  }
}

function createBoard() {
  hydrating.value = true
  activeBoard.value = null
  Object.assign(form, { name: '', description: '' })
  boardContent.value = emptyContent()
  dirty.value = false
  saveState.value = 'saved'
  drawerOpen.value = true
  void nextTick(() => { hydrating.value = false })
}

async function openBoard(summary: ResearchBoardSummary) {
  drawerOpen.value = true
  detailLoading.value = true
  hydrating.value = true
  try {
    const board = (await getResearchBoard(summary.id)).data
    activeBoard.value = board
    Object.assign(form, { name: board.name, description: board.description || '' })
    boardContent.value = structuredClone(board.content) as unknown as BoardContent
    dirty.value = false
    saveState.value = 'saved'
  } finally {
    detailLoading.value = false
    await nextTick()
    hydrating.value = false
  }
}

function scheduleAutoSave() {
  if (!activeBoard.value) return
  if (autoSaveTimer) clearTimeout(autoSaveTimer)
  autoSaveTimer = setTimeout(() => { void saveBoard(false, true) }, 1200)
}

async function saveBoard(closeAfterSave = false, quiet = false): Promise<ResearchBoard | null> {
  if (!form.name.trim()) {
    if (!quiet) message.warning('请输入白板名称')
    return null
  }
  if (saving.value) return null
  saving.value = true
  saveState.value = 'saving'
  try {
    const payload = {
      name: form.name.trim(),
      description: form.description.trim() || undefined,
      content: boardContent.value as unknown as Record<string, unknown>
    }
    const response = activeBoard.value
      ? await updateResearchBoard(activeBoard.value.id, { ...payload, version: activeBoard.value.version })
      : await createResearchBoard(payload)
    activeBoard.value = response.data
    dirty.value = false
    saveState.value = 'saved'
    await refreshBoardSummary(response.data)
    if (!quiet) message.success('白板已保存')
    if (closeAfterSave) drawerOpen.value = false
    return response.data
  } catch (error) {
    saveState.value = 'error'
    const status = (error as { response?: { status?: number } }).response?.status
    if (status === 409) message.error('白板已在其他会话更新，请关闭后重新打开')
    return null
  } finally {
    saving.value = false
  }
}

async function refreshBoardSummary(board: ResearchBoard) {
  const summary: ResearchBoardSummary = {
    id: board.id,
    owner_id: board.owner_id,
    name: board.name,
    description: board.description,
    version: board.version,
    node_count: (board.content.nodes as unknown[] | undefined)?.length ?? 0,
    created_at: board.created_at,
    updated_at: board.updated_at
  }
  const index = boards.value.findIndex(item => item.id === board.id)
  boards.value = index === -1
    ? [summary, ...boards.value]
    : boards.value.map(item => item.id === board.id ? summary : item)
}

async function removeBoard(board: ResearchBoardSummary) {
  await deleteResearchBoard(board.id)
  boards.value = boards.value.filter(item => item.id !== board.id)
  if (activeBoard.value?.id === board.id) drawerOpen.value = false
  message.success('白板已删除')
}

async function generateDraft() {
  const saved = await saveBoard(false, true)
  if (!saved) return
  const draft = await createBoardWorkflowDraft(saved.id)
  sessionStorage.setItem('research-board-workflow-draft', JSON.stringify(draft.data))
  message.success('工作流草稿已生成')
  await router.push('/workflow')
}

function handleBeforeUnload(event: BeforeUnloadEvent) {
  if (!dirty.value) return
  event.preventDefault()
  event.returnValue = ''
}

watch([() => form.name, () => form.description, boardContent], () => {
  if (hydrating.value || !drawerOpen.value) return
  dirty.value = true
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
.board-page { max-width: 1200px; margin: 0 auto; padding: @spacing-xl; }
.board-load-error { margin-bottom: @spacing-lg; }
.board-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(260px, 1fr)); gap: @spacing-md; }
.board-card { min-height: 150px; cursor: pointer; }
.board-card p { min-height: 40px; color: @text-secondary; }
.board-meta, .drawer-footer { display: flex; align-items: center; justify-content: space-between; gap: @spacing-md; }
.board-meta { color: @text-tertiary; font-size: @font-size-xs; }
.save-state { color: @text-tertiary; font-size: @font-size-sm; }
.save-state.is-error { color: @error-color; }
.save-state.is-dirty { color: @warning-color; }
</style>
