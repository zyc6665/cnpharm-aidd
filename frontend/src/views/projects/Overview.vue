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

    <a-skeleton v-if="loading && !overview" active :paragraph="{ rows: 10 }" />
    <template v-else-if="overview">
      <header class="overview-header">
        <div>
          <p class="eyebrow">项目总览</p>
          <h1>{{ overview.project.name }}</h1>
          <p>{{ overview.project.goal || '尚未设置研究目标' }}</p>
        </div>
        <div class="header-actions">
          <router-link :to="`/projects/${projectId}/research`" data-testid="open-research">
            <a-button type="primary">进入智能体研究</a-button>
          </router-link>
          <router-link :to="`/projects/${projectId}/boards`">
            <a-button>科研白板</a-button>
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
              <span
                >{{ artifactTypeLabel(artifact) }} ·
                {{ formatSize(artifact.latest_version.size_bytes) }}</span
              >
            </a>
          </div>
          <a-empty v-else :description="artifactEmptyDescription" />
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
              <span
                >{{ task.tool_name || '未知工具' }} · {{ task.status }} · {{ task.progress }}%</span
              >
            </router-link>
          </div>
          <a-empty v-else description="暂无任务" />
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
          <a-empty v-else description="暂无工作流" />
        </section>

        <section class="overview-section">
          <div class="section-heading">
            <h2>科研白板</h2>
            <router-link :to="`/projects/${projectId}/boards`">全部白板</router-link>
          </div>
          <div v-if="overview.boards.length" class="resource-list">
            <router-link
              v-for="board in overview.boards"
              :key="board.id"
              :to="`/projects/${projectId}/boards/${board.id}`"
              class="resource-row"
            >
              <strong>{{ board.name }}</strong>
              <span>{{ board.node_count }} 个对象 · {{ formatTime(board.updated_at) }}</span>
            </router-link>
          </div>
          <a-empty v-else description="暂无科研白板" />
        </section>
      </div>
    </template>
  </main>
</template>

<script setup lang="ts">
  import { computed, onMounted, ref } from 'vue'
  import { useRoute } from 'vue-router'
  import { getProjectOverview } from '@/api/projects'
  import { buildArtifactVersionDownloadUrl, getProjectArtifacts } from '@/api/artifacts'
  import ProjectWorkspaceNav from '@/components/projects/ProjectWorkspaceNav.vue'
  import {
    PROJECT_ARTIFACT_FILTER_PRESETS,
    buildProjectTaskPath,
    buildProjectWorkflowPath,
    formatProjectResourceSize,
    formatProjectResourceTime,
    getProjectArtifactTypeLabel,
    getProjectOverviewStatCards,
    type ProjectArtifactFilterPreset
  } from '@/domain/projects'
  import type { ProjectOverview } from '@/types/projects'
  import type { TypedArtifact } from '@/types/artifacts'

  const route = useRoute()
  const projectId = computed(() => String(route.params.projectId || ''))
  const projectTasksPath = computed(() => buildProjectTaskPath(projectId.value))
  const projectWorkflowPath = computed(() => buildProjectWorkflowPath(projectId.value))
  const overview = ref<ProjectOverview | null>(null)
  const loading = ref(false)
  const loadError = ref(false)
  const artifactFilterPresets = PROJECT_ARTIFACT_FILTER_PRESETS
  const activeArtifactFilterKey = ref<ProjectArtifactFilterPreset['key']>('recent')
  const artifactFilterResults = ref<TypedArtifact[] | null>(null)
  const artifactFilterLoading = ref(false)
  const artifactFilterError = ref(false)

  const statCards = computed(() => getProjectOverviewStatCards(overview.value?.counts))
  const displayedArtifacts = computed(() => artifactFilterResults.value ?? overview.value?.artifacts ?? [])
  const artifactEmptyDescription = computed(() =>
    activeArtifactFilterKey.value === 'recent' ? '暂无 Artifact' : '没有匹配的 Artifact'
  )

  async function load() {
    if (!projectId.value) return
    loading.value = true
    loadError.value = false
    try {
      overview.value = (await getProjectOverview(projectId.value)).data
      activeArtifactFilterKey.value = 'recent'
      artifactFilterResults.value = null
      artifactFilterError.value = false
    } catch {
      loadError.value = true
    } finally {
      loading.value = false
    }
  }

  async function selectArtifactFilter(preset: ProjectArtifactFilterPreset) {
    activeArtifactFilterKey.value = preset.key
    artifactFilterError.value = false
    if (!preset.params) {
      artifactFilterResults.value = null
      return
    }

    artifactFilterLoading.value = true
    try {
      artifactFilterResults.value = (await getProjectArtifacts(projectId.value, preset.params)).data.items
    } catch {
      artifactFilterResults.value = []
      artifactFilterError.value = true
    } finally {
      artifactFilterLoading.value = false
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
    max-width: 1180px;
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
    .overview-stats,
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
