<template>
  <main class="design-pipeline-page" data-testid="design-pipeline-page">
    <AppPageHeader :title="t('design.pipeline.title')" :subtitle="t('design.pipeline.subtitle')">
      <template #actions>
        <a-space>
          <a-select
            v-model:value="projectId"
            :options="projectOptions"
            :placeholder="t('design.pipeline.projectPlaceholder')"
            class="project-select"
            data-testid="design-pipeline-project"
            @change="onProjectChange"
          />
          <a-button
            type="primary"
            :disabled="!projectId"
            data-testid="design-pipeline-continue"
            @click="showGuided = !showGuided"
          >
            {{ showGuided ? t('design.pipeline.hideFlow') : t('design.pipeline.continueFlow') }}
          </a-button>
        </a-space>
      </template>
    </AppPageHeader>

    <AppInlineError
      v-if="loadError"
      data-testid="design-pipeline-error"
      :title="t('design.pipeline.loadError')"
      :description="t('common.listStates.errorDescription')"
    >
      <a-button size="small" @click="reload">{{ t('common.listStates.retry') }}</a-button>
    </AppInlineError>

    <a-empty v-else-if="!projects.length && !loading" :description="t('design.pipeline.noProject')">
      <a-button type="primary" @click="goProjects">{{ t('design.pipeline.goProjects') }}</a-button>
    </a-empty>

    <a-spin v-else :spinning="loading">
      <div v-if="nextStage" class="next-hint" data-testid="design-pipeline-next">
        {{ t('design.pipeline.nextHint', { stage: t(nextStage.labelKey) }) }}
      </div>

      <div class="pipeline-board">
        <div
          v-for="stage in stages"
          :key="stage.key"
          class="stage-card"
          :class="`is-${stage.readiness}`"
          data-testid="design-stage-card"
        >
          <div class="stage-top">
            <span class="stage-order">STEP 0{{ stage.order }}</span>
            <span class="stage-badge">{{ t(`design.pipeline.readiness.${stage.readiness}`) }}</span>
          </div>
          <h4 class="stage-name">{{ t(stage.labelKey) }}</h4>
          <p class="stage-count" data-testid="design-stage-missing-count">
            {{ t('design.pipeline.stageCount', { count: stage.count }) }}
          </p>
          <a-button
            :type="stage.readiness === 'ready' ? 'default' : 'primary'"
            class="stage-action"
            @click="goStage(stage)"
          >
            {{ stage.readiness === 'ready' ? t('design.pipeline.viewStage') : t('design.pipeline.goStage') }}
          </a-button>
        </div>
      </div>

      <div v-if="showGuided && projectId" class="guided-wrap" data-testid="design-pipeline-guided">
        <GuidedWorkflow :key="focusStage || 'default'" :project-id="projectId" :initial-step="focusStep" />
      </div>
    </a-spin>
  </main>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useRoute, useRouter } from 'vue-router'
import AppPageHeader from '@/components/common/AppPageHeader.vue'
import AppInlineError from '@/components/common/AppInlineError.vue'
import GuidedWorkflow from '@/views/workflow/GuidedWorkflow.vue'
import { listDesignProjects } from '@/api/design'
import { getProjectStage } from '@/api/decisions'
import { buildDesignStages, firstMissingStage, type DesignStageState } from '@/domain/design/pipeline'
import type { ProjectStage } from '@/types/decisions'
import type { ResearchProject } from '@/types/projects'

const route = useRoute()
const router = useRouter()
const { t } = useI18n()

const projects = ref<ResearchProject[]>([])
const projectId = ref('')
const stage = ref<ProjectStage | null>(null)
const loading = ref(false)
const loadError = ref(false)
const showGuided = ref(false)

const projectOptions = computed(() => projects.value.map(p => ({ value: p.id, label: p.name })))
const stages = computed<DesignStageState[]>(() => buildDesignStages(stage.value, projectId.value))
const nextStage = computed<DesignStageState | null>(() => firstMissingStage(stages.value))
const focusStage = computed(() => {
  const raw = route.query.focus
  return typeof raw === 'string' ? raw : ''
})
const focusStep = computed(() => (focusStage.value === 'pocket' ? 1 : 0))

function goStage(target: DesignStageState): void {
  void router.push(target.primaryPath)
}

function goProjects(): void {
  void router.push('/workspace')
}

function onProjectChange(value: unknown): void {
  if (typeof value === 'string') void loadStage(value)
}

async function loadStage(id: string): Promise<void> {
  if (!id) return
  loading.value = true
  loadError.value = false
  try {
    const response = await getProjectStage(id)
    stage.value = response.data
    localStorage.setItem('design:lastProjectId', id)
  } catch {
    loadError.value = true
    stage.value = null
  } finally {
    loading.value = false
  }
}

function resolveInitialProjectId(): string {
  const query = route.query.project_id
  if (typeof query === 'string' && query) return query
  const stored = typeof localStorage !== 'undefined' ? localStorage.getItem('design:lastProjectId') : null
  if (stored) return stored
  return projects.value[0]?.id ?? ''
}

async function loadProjects(): Promise<void> {
  loading.value = true
  loadError.value = false
  try {
    projects.value = await listDesignProjects()
  } catch {
    loadError.value = true
    projects.value = []
  } finally {
    loading.value = false
  }
}

async function reload(): Promise<void> {
  await loadProjects()
  const id = projectId.value || resolveInitialProjectId()
  projectId.value = id
  if (id) await loadStage(id)
}

onMounted(async () => {
  await loadProjects()
  projectId.value = resolveInitialProjectId()
  if (projectId.value) await loadStage(projectId.value)
  if (focusStage.value === 'structure' || focusStage.value === 'pocket') {
    showGuided.value = true
  }
})

// 已在 /design 页时，点击侧栏「结构预测/口袋预测」只改 query（path 不变），
// 组件不会重新挂载；监听 query 变化，聚焦对应阶段并展开引导。
watch(
  () => [route.query.focus, route.query.project_id],
  ([focusQuery, projectQuery]) => {
    const focus = typeof focusQuery === 'string' ? focusQuery : ''
    if (focus === 'structure' || focus === 'pocket') {
      showGuided.value = true
    }
    const pid = typeof projectQuery === 'string' ? projectQuery : ''
    if (pid && pid !== projectId.value) {
      projectId.value = pid
      void loadStage(pid)
    }
  }
)
</script>

<style scoped lang="less">
@import '@/assets/styles/variables.less';

.design-pipeline-page {
  max-width: 1280px;
  margin: 0 auto;
  padding: @spacing-xl @spacing-lg @spacing-xxl;

  .project-select {
    width: 260px;
  }

  .next-hint {
    margin-bottom: @spacing-md;
    padding: @spacing-sm @spacing-md;
    border: 1px solid @accent-color-border;
    border-radius: @border-radius-md;
    background: @accent-color-light;
    color: @accent-color;
    font-size: @font-size-sm;
  }

  .pipeline-board {
    display: flex;
    gap: @spacing-md;
    align-items: stretch;
  }

  .stage-card {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    gap: @spacing-sm;
    padding: @spacing-md;
    border: 1px solid @border-color;
    border-radius: @border-radius-lg;
    background: @bg-surface;

    &.is-ready {
      border-color: @success-color-light;
    }

    &.is-missing {
      border-style: dashed;
    }
  }

  .stage-top {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .stage-order {
    font-size: @font-size-xs;
    font-weight: @font-weight-bold;
    color: @accent-color;
  }

  .stage-badge {
    font-size: @font-size-xs;
    padding: 1px 8px;
    border-radius: 999px;
    background: @bg-elevated;
    color: @text-secondary;
  }

  .stage-name {
    margin: 0;
    font-size: @font-size-md;
    font-weight: @font-weight-semibold;
  }

  .stage-count {
    margin: 0;
    flex: 1;
    color: @text-secondary;
    font-size: @font-size-sm;
  }

  .stage-action {
    width: 100%;
  }

  .guided-wrap {
    margin-top: @spacing-lg;
  }

  @media (max-width: @screen-md) {
    .pipeline-board {
      flex-direction: column;
    }
  }
}
</style>
