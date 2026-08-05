<template>
  <div class="board-list-page">
    <ProjectWorkspaceNav v-if="projectId" :project-id="projectId" />
    <AppPageHeader title="科研白板" subtitle="项目假设、证据和科研产物">
      <template #actions><a-button type="primary" @click="createOpen = true"><PlusOutlined /> 新建白板</a-button></template>
    </AppPageHeader>
    <a-input v-model:value="keyword" class="board-search" allow-clear placeholder="搜索白板" />
    <a-alert v-if="loadError" type="error" show-icon message="科研白板加载失败">
      <template #action><a-button size="small" @click="load">重试</a-button></template>
    </a-alert>
    <a-skeleton v-else-if="loading" active :paragraph="{ rows: 6 }" />
    <a-empty v-else-if="!filteredBoards.length" description="暂无科研白板" />
    <div v-else class="board-list">
      <article v-for="item in filteredBoards" :key="item.id">
        <button :data-testid="`open-board-${item.id}`" type="button" @click="openBoard(item)">
          <span class="board-name">{{ item.name }}</span>
          <span class="board-description">{{ item.description || '尚未添加研究说明' }}</span>
          <span class="board-meta">{{ item.node_count }} 个对象 · {{ formatDate(item.updated_at) }}</span>
        </button>
        <a-popconfirm title="确定删除这个白板？" @confirm="removeBoard(item)">
          <a-button type="text" danger title="删除"><DeleteOutlined /></a-button>
        </a-popconfirm>
      </article>
    </div>

    <a-modal v-model:open="createOpen" title="新建科研白板" :confirm-loading="creating" @ok="createBoard">
      <a-input v-model:value="draft.name" :maxlength="160" placeholder="白板名称" />
      <a-textarea v-model:value="draft.description" :rows="3" :maxlength="2000" placeholder="研究说明" />
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import dayjs from 'dayjs'
import { message } from 'ant-design-vue'
import { DeleteOutlined, PlusOutlined } from '@ant-design/icons-vue'
import AppPageHeader from '@/components/common/AppPageHeader.vue'
import ProjectWorkspaceNav from '@/components/projects/ProjectWorkspaceNav.vue'
import {
  createResearchBoard,
  deleteResearchBoard,
  getResearchBoards,
  type ResearchBoardSummary,
} from '@/api/research-boards'

const route = useRoute()
const router = useRouter()
const boards = ref<ResearchBoardSummary[]>([])
const loading = ref(false)
const loadError = ref(false)
const keyword = ref('')
const createOpen = ref(false)
const creating = ref(false)
const draft = reactive({ name: '', description: '' })
const projectId = computed(() => typeof route.params.projectId === 'string' ? route.params.projectId : undefined)
const filteredBoards = computed(() => {
  const query = keyword.value.trim().toLocaleLowerCase()
  if (!query) return boards.value
  return boards.value.filter(item => `${item.name} ${item.description || ''}`.toLocaleLowerCase().includes(query))
})
const formatDate = (value: string) => dayjs(value).format('YYYY-MM-DD HH:mm')

async function load() {
  loading.value = true
  loadError.value = false
  try {
    boards.value = (await getResearchBoards(projectId.value)).data.items
  } catch {
    loadError.value = true
  } finally {
    loading.value = false
  }
}

type BoardNavigationTarget = Pick<ResearchBoardSummary, 'id' | 'project_id'>

function openBoard(item: BoardNavigationTarget) {
  const ownerProjectId = projectId.value || item.project_id
  void router.push(ownerProjectId
    ? `/projects/${ownerProjectId}/boards/${item.id}`
    : `/research-boards/${item.id}`)
}

async function createBoard() {
  if (!draft.name.trim()) {
    message.warning('请输入白板名称')
    return
  }
  creating.value = true
  try {
    const response = await createResearchBoard({
      name: draft.name.trim(),
      description: draft.description.trim() || undefined,
      project_id: projectId.value,
      content: { nodes: [], edges: [], viewport: { x: 0, y: 0, zoom: 1 } },
    })
    createOpen.value = false
    openBoard(response.data)
  } finally {
    creating.value = false
  }
}

async function removeBoard(item: ResearchBoardSummary) {
  await deleteResearchBoard(item.id)
  boards.value = boards.value.filter(board => board.id !== item.id)
  message.success('白板已删除')
}

onMounted(() => { void load() })
</script>

<style scoped lang="less">
@import '@/assets/styles/variables.less';
.board-list-page { max-width: 1120px; margin: 0 auto; padding: @spacing-xl; }
.board-search { width: min(360px, 100%); margin-bottom: @spacing-lg; }
.board-list { border-top: 1px solid @border-color; }
.board-list article { display: flex; align-items: center; border-bottom: 1px solid @border-color; }
.board-list article > button:first-child { min-width: 0; flex: 1; display: grid; grid-template-columns: minmax(160px, .7fr) minmax(200px, 1fr) auto; align-items: center; gap: @spacing-md; padding: @spacing-md; border: 0; background: transparent; text-align: left; cursor: pointer; }
.board-list article > button:first-child:hover { background: @bg-hover; }
.board-name { color: @text-primary; font-weight: @font-weight-semibold; }
.board-description { overflow: hidden; color: @text-secondary; text-overflow: ellipsis; white-space: nowrap; }
.board-meta { color: @text-tertiary; font-size: @font-size-xs; white-space: nowrap; }
:deep(.ant-modal-body) { display: grid; gap: @spacing-md; }
@media (max-width: 720px) { .board-list article > button:first-child { grid-template-columns: 1fr; gap: 4px; } }
</style>
