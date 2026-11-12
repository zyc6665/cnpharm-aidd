<template>
  <main class="project-overview-page">
    <router-link to="/workspace" class="back-link">返回工作台</router-link>
    <ProjectWorkspaceNav :project-id="projectId" />

    <a-alert
      v-if="loadError"
      class="overview-alert"
      type="error"
      show-icon
      message="项目总览加载失败"
    >
      <template #action><a-button size="small" @click="load">重试</a-button></template>
    </a-alert>

    <!-- 归档项目能打开、能看，缺的只是「撤销」。横幅就是那个入口。 -->
    <a-alert
      v-if="isArchived"
      class="overview-alert"
      type="warning"
      show-icon
      message="该项目已归档"
      description="归档只表示它不在工作台的常用列表里，项目数据、任务与产物都保留。撤销归档后可以继续提交任务。"
      data-testid="project-archived-banner"
    >
      <template #action>
        <a-button
          v-if="canUnarchive"
          size="small"
          :loading="unarchiving"
          data-testid="project-unarchive-action"
          @click="handleUnarchive"
        >
          撤销归档
        </a-button>
      </template>
    </a-alert>

    <a-skeleton v-if="loading && !overview" active :paragraph="{ rows: 10 }" />
    <template v-else-if="overview">
      <header class="overview-header">
        <div>
          <p class="eyebrow">项目总览</p>
          <h1>{{ overview.project.name }}</h1>
          <p>{{ overview.project.goal || '尚未设置研究目标' }}</p>
        </div>
        <div class="header-actions">
          <router-link :to="`/projects/${projectId}/targets`" data-testid="open-targets">
            <a-button type="primary">进入靶点分析</a-button>
          </router-link>
          <router-link :to="`/projects/${projectId}/settings`">
            <a-button>项目设置</a-button>
          </router-link>
        </div>
      </header>

      <section class="overview-stats">
        <article v-for="item in statCards" :key="item.label">
          <strong>{{ item.value }}</strong>
          <span>{{ item.label }}</span>
        </article>
      </section>

      <div class="overview-grid">
        <section class="overview-section">
          <div class="section-heading">
            <h2>Artifact 检索</h2>
            <router-link :to="`/projects/${projectId}/lineage`">Artifact 谱系</router-link>
          </div>
          <div class="artifact-filter-bar" data-testid="artifact-filter-bar">
            <button
              v-for="preset in artifactFilterPresets"
              :key="preset.key"
              type="button"
              data-testid="artifact-filter-preset"
              class="artifact-filter-preset"
              :class="{ 'is-active': preset.key === activeArtifactFilterKey }"
              :disabled="artifactFilterLoading"
              @click="selectArtifactFilter(preset)"
            >
              {{ preset.label }}
            </button>
          </div>
          <a-alert
            v-if="artifactFilterError"
            class="overview-alert"
            type="error"
            show-icon
            message="Artifact 检索失败"
          />
          <div v-if="displayedArtifacts.length" class="resource-list">
            <a
              v-for="artifact in displayedArtifacts"
              :key="artifact.id"
              :href="artifactDownloadUrl(artifact)"
              class="resource-row"
            >
              <strong>{{ artifact.name }}</strong>
              <span>
                {{ artifactTypeLabel(artifact) }} ·
                {{ formatSize(artifact.latest_version.size_bytes) }}
              </span>
            </a>
          </div>
          <div v-if="displayedArtifacts.length" class="artifact-list-footer">
            <a-button
              v-if="artifactHasMore"
              size="small"
              :loading="artifactLoadingMore"
              data-testid="artifact-load-more"
              @click="loadMoreArtifacts"
            >
              加载更多
            </a-button>
            <span v-else data-testid="artifact-all-loaded">已全部加载</span>
          </div>
          <AppEmptyState
            v-else
            :title="activeArtifactFilterKey === 'recent' ? '还没有产出物' : '没有匹配的产出物'"
            :description="
              activeArtifactFilterKey === 'recent'
                ? 'Artifact 是任务与工作流的产出沉淀：结构、口袋、分子表、运行报告都会自动归档到这里，可回溯到产生它的那次执行。'
                : '换个筛选条件试试，或先清除筛选查看全部产出物。'
            "
            size="compact"
          >
            <a-button v-if="activeArtifactFilterKey !== 'recent'" size="small" @click="clearArtifactFilter">
              查看全部产出物
            </a-button>
            <router-link v-else :to="projectTargetsPath">
              <a-button size="small" type="primary">先从靶点开始</a-button>
            </router-link>
          </AppEmptyState>
        </section>

        <section class="overview-section">
          <div class="section-heading">
            <h2>最近任务</h2>
            <router-link :to="projectTasksPath">全部任务</router-link>
          </div>
          <div v-if="overview.tasks.length" class="resource-list">
            <router-link
              v-for="task in overview.tasks"
              :key="task.id"
              :to="`/tasks/${task.id}`"
              class="resource-row"
            >
              <strong>{{ task.name || task.tool_name || task.id }}</strong>
              <span>{{ task.tool_name || '未知工具' }} · {{ task.status }} · {{ task.progress }}%</span>
            </router-link>
          </div>
          <AppEmptyState
            v-else
            title="还没有执行任务"
            description="任务按工具版本执行：提交后进入队列、分配算力、产出结果，全过程可追溯。"
            size="compact"
          >
            <router-link :to="projectWorkflowPath">
              <a-button size="small" type="primary">从工作流模板开始</a-button>
            </router-link>
          </AppEmptyState>
        </section>

        <section class="overview-section">
          <div class="section-heading">
            <h2>项目工作流</h2>
            <router-link :to="projectWorkflowPath">打开工作流</router-link>
          </div>
          <div v-if="overview.workflows.length" class="resource-list">
            <router-link
              v-for="workflow in overview.workflows"
              :key="workflow.id"
              :to="projectWorkflowPath"
              class="resource-row"
            >
              <strong>{{ workflow.name }}</strong>
              <span>{{ workflow.status }} · {{ formatTime(workflow.updated_at) }}</span>
            </router-link>
          </div>
          <AppEmptyState
            v-else
            title="还没有工作流"
            description="工作流把多个工具串成一条链路，一次提交按依赖顺序执行，节点状态与产物自动回填。"
            size="compact"
          >
            <router-link :to="projectWorkflowPath">
              <a-button size="small">打开工作流</a-button>
            </router-link>
          </AppEmptyState>
        </section>

      </div>
    </template>
  </main>
</template>

<script setup lang="ts">
  import { computed, onMounted, ref } from 'vue'
  import { useRoute, useRouter } from 'vue-router'
  import { message } from 'ant-design-vue'
  import { getProjectOverview, unarchiveProject } from '@/api/projects'
  import { buildArtifactVersionDownloadUrl, getProjectArtifacts } from '@/api/artifacts'
  import { mergeCursorPage } from '@/utils/pagination'
  import ProjectWorkspaceNav from '@/components/projects/ProjectWorkspaceNav.vue'
  import AppEmptyState from '@/components/common/AppEmptyState.vue'
  import {
    PROJECT_ARTIFACT_FILTER_PRESETS,
    buildProjectTaskPath,
    buildProjectTargetsPath,
    buildProjectWorkflowPath,
    formatProjectResourceSize,
    formatProjectResourceTime,
    getProjectArtifactTypeLabel,
    getProjectOverviewStatCards,
    resolveProjectArtifactFilterPreset,
    type ProjectArtifactFilterPreset
  } from '@/domain/projects'
  import type { ProjectOverview } from '@/types/projects'
  import type { TypedArtifact } from '@/types/artifacts'

  const route = useRoute()
  const router = useRouter()
  const projectId = computed(() => String(route.params.projectId || ''))
  const projectTasksPath = computed(() => buildProjectTaskPath(projectId.value))
  const projectWorkflowPath = computed(() => buildProjectWorkflowPath(projectId.value))
  const projectTargetsPath = computed(() => buildProjectTargetsPath(projectId.value))
  const overview = ref<ProjectOverview | null>(null)
  const loading = ref(false)
  const loadError = ref(false)
  const unarchiving = ref(false)
  const artifactFilterPresets = PROJECT_ARTIFACT_FILTER_PRESETS
  const activeArtifactFilterKey = ref<ProjectArtifactFilterPreset['key']>('recent')
  const artifactPageSize = 20
  const artifactItems = ref<TypedArtifact[] | null>(null)
  const artifactNextCursor = ref<string | null>(null)
  const artifactHasMore = ref(false)
  const artifactFilterLoading = ref(false)
  const artifactLoadingMore = ref(false)
  const artifactFilterError = ref(false)

  const statCards = computed(() => getProjectOverviewStatCards(overview.value?.counts))
  const isArchived = computed(() => overview.value?.project.status === 'archived')
  const canUnarchive = computed(() =>
    ['owner', 'editor', 'admin'].includes(overview.value?.project.role ?? '')
  )

  async function handleUnarchive() {
    if (unarchiving.value || !projectId.value) return
    unarchiving.value = true
    try {
      await unarchiveProject(projectId.value)
      message.success('已撤销归档')
      await load()
    } catch {
      message.error('撤销归档失败，请重试')
    } finally {
      unarchiving.value = false
    }
  }
  const displayedArtifacts = computed(
    () => artifactItems.value ?? overview.value?.artifacts ?? []
  )
  /** 把「没有匹配」退回「最近」——空状态里的按钮要有真实动作，不能只是装饰。 */
  function clearArtifactFilter() {
    void selectArtifactFilter(PROJECT_ARTIFACT_FILTER_PRESETS[0]!)
  }

  async function load() {
    if (!projectId.value) return
    loading.value = true
    loadError.value = false
    try {
      overview.value = (await getProjectOverview(projectId.value)).data
      const preset = resolveProjectArtifactFilterPreset(route.query.artifact_filter)
      await selectArtifactFilter(preset, false)
    } catch {
      loadError.value = true
    } finally {
      loading.value = false
    }
  }

  async function selectArtifactFilter(preset: ProjectArtifactFilterPreset, syncRoute = true) {
    activeArtifactFilterKey.value = preset.key
    artifactFilterError.value = false
    if (syncRoute) {
      void router.replace({
        query: {
          ...route.query,
          artifact_filter: preset.key === 'recent' ? undefined : preset.key
        }
      })
    }
    // 切换筛选：重置游标与列表，再走首屏 offset 请求。
    artifactItems.value = []
    artifactNextCursor.value = null
    artifactHasMore.value = false
    await loadArtifactPage(preset)
  }

  /** 首屏 offset 请求（兼容旧行为），同时接出游标供「加载更多」使用。 */
  async function loadArtifactPage(preset: ProjectArtifactFilterPreset) {
    if (!projectId.value) return
    artifactFilterLoading.value = true
    try {
      const response = await getProjectArtifacts(projectId.value, {
        ...(preset.params ?? {}),
        page: 1,
        page_size: artifactPageSize
      })
      const state = mergeCursorPage(
        { items: [], nextCursor: null, hasMore: false },
        response.data,
        artifact => artifact.id
      )
      artifactItems.value = state.items
      artifactNextCursor.value = state.nextCursor
      artifactHasMore.value = state.hasMore
    } catch {
      artifactItems.value = []
      artifactNextCursor.value = null
      artifactHasMore.value = false
      artifactFilterError.value = true
    } finally {
      artifactFilterLoading.value = false
    }
  }

  /** 加载更多：带 cursor 请求并去重追加。 */
  async function loadMoreArtifacts() {
    if (
      !projectId.value ||
      !artifactHasMore.value ||
      artifactLoadingMore.value ||
      !artifactNextCursor.value
    ) {
      return
    }

    const preset = resolveProjectArtifactFilterPreset(activeArtifactFilterKey.value)
    artifactLoadingMore.value = true
    try {
      const response = await getProjectArtifacts(projectId.value, {
        ...(preset.params ?? {}),
        page_size: artifactPageSize,
        cursor: artifactNextCursor.value
      })
      const state = mergeCursorPage(
        {
          items: artifactItems.value ?? [],
          nextCursor: artifactNextCursor.value,
          hasMore: artifactHasMore.value
        },
        response.data,
        artifact => artifact.id,
        { append: true }
      )
      artifactItems.value = state.items
      artifactNextCursor.value = state.nextCursor
      artifactHasMore.value = state.hasMore
    } catch {
      artifactFilterError.value = true
    } finally {
      artifactLoadingMore.value = false
    }
  }

  const artifactDownloadUrl = (artifact: TypedArtifact) =>
    buildArtifactVersionDownloadUrl(artifact.id, artifact.latest_version.id)
  const artifactTypeLabel = getProjectArtifactTypeLabel
  const formatTime = formatProjectResourceTime
  const formatSize = formatProjectResourceSize

  onMounted(() => {
    void load()
  })
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .project-overview-page {
    max-width: @page-max-width;
    margin: 0 auto;
    padding: @spacing-xl @spacing-lg @spacing-xxl;
  }
  .back-link {
    display: inline-block;
    margin-bottom: @spacing-lg;
    color: @text-tertiary;
  }
  .overview-alert {
    margin-bottom: @spacing-lg;
  }
  .overview-header {
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    gap: @spacing-xl;
    margin-bottom: @spacing-xl;
  }
  .overview-header h1 {
    margin: 0;
    color: @text-primary;
    font-size: @font-size-xxl;
    line-height: @line-height-tight;
    letter-spacing: 0;
  }
  .overview-header p {
    margin: @spacing-xs 0 0;
    color: @text-tertiary;
  }
  .eyebrow {
    color: @accent-color !important;
    font-size: @font-size-xs;
    font-weight: @font-weight-bold;
    text-transform: uppercase;
  }
  .header-actions {
    display: flex;
    gap: @spacing-sm;
  }
  .overview-stats {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: @spacing-lg;
    margin-bottom: @spacing-xl;
  }
  .overview-stats article {
    padding: @spacing-lg;
    border: 1px solid @border-color;
    border-radius: @border-radius-md;
    background: @bg-elevated;
  }
  .overview-stats strong,
  .overview-stats span {
    display: block;
  }
  .overview-stats strong {
    color: @text-primary;
    font-size: @font-size-xl;
  }
  .overview-stats span {
    margin-top: @spacing-xs;
    color: @text-tertiary;
  }
  .overview-grid {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: @spacing-xxl;
  }
  .overview-section {
    min-width: 0;
  }
  .section-heading {
    display: flex;
    align-items: center;
    justify-content: space-between;
    min-height: 40px;
    margin-bottom: @spacing-md;
  }
  .section-heading h2 {
    margin: 0;
    color: @text-primary;
    font-size: @font-size-md;
    letter-spacing: 0;
  }
  .section-heading a {
    color: @text-tertiary;
    font-size: @font-size-sm;
  }
  .artifact-filter-bar {
    display: flex;
    flex-wrap: wrap;
    gap: @spacing-xs;
    margin-bottom: @spacing-sm;
  }
  .artifact-filter-preset {
    padding: 4px 9px;
    color: @text-secondary;
    border: 1px solid @border-color;
    border-radius: @border-radius-base;
    background: @bg-elevated;
    font-size: @font-size-xs;
    cursor: pointer;
  }
  .artifact-filter-preset:hover,
  .artifact-filter-preset.is-active {
    color: @accent-color;
    border-color: @accent-color;
    background: @accent-color-light;
  }
  .artifact-filter-preset:disabled {
    cursor: wait;
    opacity: 0.6;
  }
  .resource-list {
    border-top: 1px solid @border-color;
  }
  .artifact-list-footer {
    display: flex;
    justify-content: center;
    margin-top: @spacing-sm;
    color: @text-tertiary;
    font-size: @font-size-sm;
  }
  .resource-row {
    display: block;
    min-height: 58px;
    padding: @spacing-sm;
    color: inherit;
    border-bottom: 1px solid @border-color;
    transition: background @transition-fast;
  }
  .resource-row:hover {
    background: @bg-hover;
  }
  .resource-row strong,
  .resource-row span {
    display: block;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
  .resource-row strong {
    color: @text-primary;
    font-size: @font-size-sm;
  }
  .resource-row span {
    margin-top: 2px;
    color: @text-tertiary;
    font-size: @font-size-xs;
  }

  @media (max-width: @screen-md) {
    .overview-header {
      align-items: flex-start;
      flex-direction: column;
    }
    .overview-stats {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
    .overview-grid {
      grid-template-columns: 1fr;
    }
  }
  @media (max-width: @screen-sm) {
    .project-overview-page {
      padding: @spacing-lg @spacing-md;
    }
    .header-actions {
      width: 100%;
      flex-direction: column;
    }
  }
</style>
