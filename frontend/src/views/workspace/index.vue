<template>
  <div class="workspace-page">
    <header class="ws-header">
      <div>
        <h1 class="ws-title">{{ greeting }}</h1>
        <p class="ws-date">{{ today }}</p>
      </div>
      <a-button type="primary" @click="$router.push('/tools')">
        <PlusOutlined /> {{ t('command.newTask') }}
      </a-button>
    </header>

    <a-alert
      v-if="overviewError"
      class="ws-error"
      type="error"
      show-icon
      message="工作台数据加载失败"
      description="请检查网络连接后重试。"
    >
      <template #action><a-button size="small" @click="loadOverview">重试</a-button></template>
    </a-alert>

    <a-skeleton v-if="overviewLoading && !hasOverview" active :paragraph="{ rows: 8 }" />
    <template v-else>
      <section class="status-strip" aria-label="任务状态概览">
        <router-link v-for="item in statusItems" :key="item.status" to="/tasks" class="status-item">
          <span class="status-dot" :class="`status-${taskStatusClass(item.status)}`"></span>
          <span>{{ item.label }}</span>
          <strong>{{ item.count }}</strong>
        </router-link>
      </section>

      <div class="ws-grid">
        <section class="ws-section">
          <div class="ws-section-head">
            <h2 class="ws-section-title">{{ t('workspace.recentTasks') }}</h2>
            <router-link to="/tasks" class="ws-section-link">{{ t('common.more') }}</router-link>
          </div>
          <div v-if="recentTasks.length" class="ws-task-list">
            <router-link
              v-for="task in recentTasks"
              :key="task.id"
              :to="`/tasks/${task.id}`"
              class="ws-task-row"
            >
              <span class="status-dot" :class="`status-${taskStatusClass(task.status)}`"></span>
              <div class="ws-task-info">
                <strong>{{ task.name || task.tool_name || t('tasks.unknownTool') }}</strong>
                <span>{{ task.tool_name || task.tool_slug || task.tool_id }}</span>
              </div>
              <a-progress
                v-if="task.status === 'running'"
                class="task-progress"
                :percent="task.progress"
                :show-info="false"
                size="small"
              />
              <time class="ws-task-time">{{ formatTaskTime(task.updated_at) }}</time>
            </router-link>
          </div>
          <div v-else class="ws-empty">
            <ExperimentOutlined class="ws-empty-icon" />
            <p>{{ t('workspace.noRecentTasks') }}</p>
            <a-button type="link" @click="$router.push('/tools')">{{ t('workspace.startFirst') }}</a-button>
          </div>
        </section>

        <section class="ws-section">
          <div class="ws-section-head"><h2 class="ws-section-title">恢复工作</h2></div>
          <div class="resume-grid">
            <div class="resume-column">
              <h3>需要处理的任务 <span>{{ overview.attention_task_count }}</span></h3>
              <div v-if="attentionTasks.length" class="resume-list">
                <div v-for="task in attentionTasks" :key="task.id" class="resume-item">
                  <router-link :to="`/tasks/${task.id}`">{{ task.name || task.tool_name || task.id }}</router-link>
                  <a-button
                    v-if="task.status === 'failure'"
                    size="small"
                    :loading="actionTaskId === task.id"
                    :disabled="Boolean(actionTaskId)"
                    @click="retry(task.id)"
                  >重试</a-button>
                  <a-button
                    v-else
                    size="small"
                    danger
                    :loading="actionTaskId === task.id"
                    :disabled="Boolean(actionTaskId)"
                    @click="cancel(task.id)"
                  >取消</a-button>
                </div>
              </div>
              <a-empty v-else :image="simpleImage" description="暂无待处理任务" />
            </div>
            <div class="resume-column">
              <h3>最近画布</h3>
              <div v-if="overview.boards.length || overview.workflows.length" class="resume-list">
                <router-link
                  v-for="board in overview.boards"
                  :key="`board-${board.id}`"
                  :to="{ path: '/research-boards', query: { board: board.id } }"
                  class="resource-row"
                >
                  <span>{{ board.name }}</span><small>{{ board.node_count }} 个节点</small>
                </router-link>
                <router-link
                  v-for="workflow in overview.workflows"
                  :key="`workflow-${workflow.id}`"
                  to="/workflow"
                  class="resource-row"
                >
                  <span>{{ workflow.name }}</span><small>工作流</small>
                </router-link>
              </div>
              <a-empty v-else :image="simpleImage" description="暂无画布" />
            </div>
            <div class="resume-column">
              <h3>最近文件</h3>
              <div v-if="overview.files.length" class="resume-list">
                <a
                  v-for="file in overview.files"
                  :key="file.id"
                  :href="`/api/v1/files/${file.id}/download`"
                  class="resource-row"
                >
                  <span>{{ file.filename }}</span><small>{{ formatFileSize(file.size_bytes) }}</small>
                </a>
              </div>
              <a-empty v-else :image="simpleImage" description="暂无文件" />
            </div>
          </div>
        </section>

        <section class="ws-section utility-grid">
          <div>
            <div class="ws-section-head"><h2 class="ws-section-title">{{ t('workspace.quickActions') }}</h2></div>
            <div class="ws-quick-grid">
              <button v-for="action in quickActions" :key="action.path" class="ws-quick-button" @click="$router.push(action.path)">
                <component :is="action.icon" />
                <span>{{ action.label }}</span>
              </button>
            </div>
          </div>
          <div>
            <div class="ws-section-head"><h2 class="ws-section-title">常用工具</h2></div>
            <div v-if="overview.frequent_tools.length" class="frequent-tools">
              <router-link v-for="tool in overview.frequent_tools" :key="tool.id" :to="`/tools/${tool.id}`">
                <span>{{ tool.name }}</span><small>使用 {{ tool.usage_count }} 次</small>
              </router-link>
            </div>
            <a-empty v-else :image="simpleImage" description="运行工具后将在这里显示" />
          </div>
        </section>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import dayjs from 'dayjs'
import { Empty, message } from 'ant-design-vue'
import { useI18n } from 'vue-i18n'
import { cancelTask, retryTask } from '@/api/tasks'
import { getWorkspaceOverview, type WorkspaceOverview } from '@/api/workspace'
import type { TaskStatus } from '@/types/models'
import {
  PlusOutlined,
  ExperimentOutlined,
  ApartmentOutlined,
  AppstoreOutlined,
} from '@ant-design/icons-vue'

const { t } = useI18n()
const simpleImage = Empty.PRESENTED_IMAGE_SIMPLE
const overviewLoading = ref(false)
const overviewError = ref(false)
const actionTaskId = ref('')
const emptyCounts = (): Record<TaskStatus, number> => ({ pending: 0, running: 0, success: 0, failure: 0, canceled: 0 })
const overview = ref<WorkspaceOverview>({
  attention_task_count: 0,
  task_status_counts: emptyCounts(),
  tasks: [],
  boards: [],
  workflows: [],
  files: [],
  frequent_tools: [],
})

const greeting = computed(() => {
  const hour = new Date().getHours()
  if (hour < 12) return t('workspace.goodMorning')
  if (hour < 18) return t('workspace.goodAfternoon')
  return t('workspace.goodEvening')
})
const today = computed(() => new Date().toLocaleDateString(
  document.documentElement.lang === 'zh' ? 'zh-CN' : 'en-US',
  { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' },
))
const hasOverview = computed(() => overview.value.tasks.length > 0 || overview.value.boards.length > 0)
const recentTasks = computed(() => overview.value.tasks.slice(0, 5))
const attentionTasks = computed(() => overview.value.tasks.filter(task => ['pending', 'running', 'failure'].includes(task.status)))
const statusItems = computed(() => [
  { status: 'pending' as const, label: '等待中', count: overview.value.task_status_counts.pending },
  { status: 'running' as const, label: '运行中', count: overview.value.task_status_counts.running },
  { status: 'failure' as const, label: '失败', count: overview.value.task_status_counts.failure },
  { status: 'success' as const, label: '已完成', count: overview.value.task_status_counts.success },
])
const quickActions = computed(() => [
  { path: '/workflow', label: t('workspace.newWorkflow'), icon: ApartmentOutlined },
  { path: '/tools', label: t('workspace.browseTools'), icon: AppstoreOutlined },
  { path: '/tasks', label: t('workspace.viewTasks'), icon: ExperimentOutlined },
  { path: '/research-boards', label: '科研白板', icon: ApartmentOutlined },
])

const taskStatusClass = (status: TaskStatus) => status === 'success' ? 'completed' : status === 'failure' ? 'failed' : status
const formatTaskTime = (time: string) => dayjs(time).format('YYYY-MM-DD HH:mm')
const formatFileSize = (bytes: number) => bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`

async function loadOverview() {
  overviewLoading.value = true
  overviewError.value = false
  try {
    overview.value = (await getWorkspaceOverview()).data
  } catch {
    overviewError.value = true
  } finally {
    overviewLoading.value = false
  }
}

async function runTaskAction(id: string, action: () => Promise<unknown>, successMessage: string) {
  if (actionTaskId.value) return
  actionTaskId.value = id
  try {
    await action()
    message.success(successMessage)
    await loadOverview()
  } finally {
    actionTaskId.value = ''
  }
}
const cancel = (id: string) => runTaskAction(id, () => cancelTask(id), '任务已取消')
const retry = (id: string) => runTaskAction(id, () => retryTask(id), '任务已重新提交')

onMounted(() => { void loadOverview() })
</script>

<style scoped lang="less">
@import '@/assets/styles/variables.less';

.workspace-page { max-width: 1120px; margin: 0 auto; padding: @spacing-xxl @spacing-lg; }
.ws-header { display: flex; align-items: flex-start; justify-content: space-between; gap: @spacing-lg; margin-bottom: @spacing-xl; }
.ws-title { margin: 0; color: @text-primary; font-size: @font-size-xxl; font-weight: @font-weight-bold; letter-spacing: 0; line-height: @line-height-tight; }
.ws-date { margin: @spacing-xs 0 0; color: @text-tertiary; font-size: @font-size-sm; }
.ws-error { margin-bottom: @spacing-lg; }
.status-strip { display: grid; grid-template-columns: repeat(4, 1fr); border-block: 1px solid @border-color; margin-bottom: @spacing-xl; }
.status-item { display: grid; grid-template-columns: auto 1fr auto; align-items: center; gap: @spacing-sm; padding: @spacing-md; color: @text-secondary; border-right: 1px solid @border-color; }
.status-item:last-child { border-right: 0; }
.status-item strong { color: @text-primary; font-size: @font-size-lg; }
.status-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.status-completed { background: @success-color; }
.status-running { background: @accent-color; }
.status-failed { background: @error-color; }
.status-pending { background: @warning-color; }
.status-canceled { background: @text-disabled; }
.ws-grid { display: flex; flex-direction: column; gap: @spacing-xl; }
.ws-section { padding-bottom: @spacing-xl; border-bottom: 1px solid @border-color; }
.ws-section:last-child { border-bottom: 0; }
.ws-section-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: @spacing-md; }
.ws-section-title { margin: 0; color: @text-primary; font-size: @font-size-md; font-weight: @font-weight-semibold; }
.ws-section-link { color: @text-tertiary; font-size: @font-size-sm; }
.ws-task-list, .resume-list, .frequent-tools { display: flex; flex-direction: column; }
.ws-task-row { display: flex; align-items: center; gap: @spacing-sm; min-height: 52px; padding: @spacing-sm; color: inherit; border-bottom: 1px solid @border-color; }
.ws-task-row:hover, .resource-row:hover, .frequent-tools a:hover { background: @bg-hover; }
.ws-task-info { flex: 1; min-width: 0; }
.ws-task-info strong, .ws-task-info span { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.ws-task-info strong { color: @text-primary; font-size: @font-size-sm; }
.ws-task-info span, .ws-task-time, .resource-row small, .frequent-tools small { color: @text-tertiary; font-size: @font-size-xs; }
.task-progress { width: 100px; }
.ws-task-time { white-space: nowrap; }
.ws-empty { padding: @spacing-xl 0; color: @text-tertiary; text-align: center; }
.ws-empty p { margin: @spacing-sm 0; }
.ws-empty-icon { color: @text-disabled; font-size: 32px; }
.resume-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: @spacing-xl; }
.resume-column { min-width: 0; }
.resume-column h3 { margin: 0 0 @spacing-sm; font-size: @font-size-sm; }
.resume-column h3 span { color: @text-tertiary; font-weight: normal; }
.resume-item, .resource-row, .frequent-tools a { display: flex; align-items: center; justify-content: space-between; gap: @spacing-sm; min-height: 38px; padding: @spacing-xs; border-bottom: 1px solid @border-color; }
.resume-item a, .resource-row span, .frequent-tools span { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.utility-grid { display: grid; grid-template-columns: 2fr 1fr; gap: @spacing-xl; }
.ws-quick-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: @spacing-sm; }
.ws-quick-button { display: flex; align-items: center; gap: @spacing-sm; min-height: 44px; padding: @spacing-sm @spacing-md; color: @text-secondary; background: @bg-hover; border: 1px solid @border-color; border-radius: @border-radius-md; cursor: pointer; font: inherit; }
.ws-quick-button:hover { color: @text-primary; border-color: @accent-color-border; }
.ws-quick-button :deep(.anticon) { color: @accent-color; font-size: 18px; }

@media (max-width: @screen-md) {
  .resume-grid, .utility-grid { grid-template-columns: 1fr; }
  .ws-quick-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
}
@media (max-width: @screen-sm) {
  .workspace-page { padding: @spacing-lg @spacing-md; }
  .status-strip { grid-template-columns: repeat(2, 1fr); }
  .status-item:nth-child(2) { border-right: 0; }
  .status-item:nth-child(-n + 2) { border-bottom: 1px solid @border-color; }
  .task-progress { display: none; }
  .ws-task-time { display: none; }
}
</style>
