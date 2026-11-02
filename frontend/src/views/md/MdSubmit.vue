<template>
  <div class="md-submit" data-testid="md-submit-page">
    <app-page-header :title="t('md.submit.title')" :subtitle="t('md.submit.subtitle')" />

    <a-card :bordered="false" class="md-submit__card">
      <a-spin :spinning="loadingProjects">
        <a-empty v-if="!loadingProjects && projects.length === 0" :description="t('md.submit.emptyProject')" />

        <a-form v-else layout="vertical" class="md-submit__form">
          <a-row :gutter="16">
            <a-col :xs="24" :md="12">
              <a-form-item :label="t('md.submit.project')" required>
                <a-select
                  v-model:value="form.projectId"
                  :placeholder="t('md.submit.projectPlaceholder')"
                  show-search
                  option-filter-prop="label"
                  :options="projectOptions"
                  data-testid="md-project-select"
                />
              </a-form-item>
            </a-col>
            <a-col :xs="24" :md="12">
              <a-form-item :label="t('md.submit.target')">
                <a-select
                  v-model:value="form.targetId"
                  :placeholder="t('md.submit.targetPlaceholder')"
                  :disabled="!form.projectId"
                  :loading="loadingTargets"
                  :options="targetOptions"
                  not-found-content="—"
                  data-testid="md-target-select"
                />
              </a-form-item>
            </a-col>
            <a-col :xs="24" :md="12">
              <a-form-item :label="t('md.submit.protein')">
                <a-select
                  v-model:value="form.proteinId"
                  :placeholder="t('md.submit.proteinPlaceholder')"
                  :disabled="!form.targetId"
                  :loading="loadingProteins"
                  :options="proteinOptions"
                  not-found-content="—"
                  data-testid="md-protein-select"
                />
              </a-form-item>
            </a-col>
            <a-col :xs="24" :md="12">
              <a-form-item :label="t('md.submit.structure')" required>
                <a-select
                  v-model:value="form.structureId"
                  :placeholder="t('md.submit.structurePlaceholder')"
                  :disabled="!form.proteinId"
                  :loading="loadingStructures"
                  :options="structureOptions"
                  not-found-content="—"
                  data-testid="md-structure-select"
                />
              </a-form-item>
            </a-col>
          </a-row>

          <div v-if="selectedStructure" class="md-submit__structure">
            <a-tag :color="selectedStructure.prepared_file_id ? 'green' : 'default'">
              {{ selectedStructure.prepared_file_id ? t('md.submit.prepared') : t('md.submit.raw') }}
            </a-tag>
            <span class="md-submit__structure-id">ID: {{ selectedStructure.id }}</span>
            <span v-if="selectedStructure.source_type" class="md-submit__structure-src">
              {{ selectedStructure.source_type }}
            </span>
          </div>
          <p class="md-submit__hint">{{ t('md.submit.selectHint') }}</p>

          <a-divider orientation="left">{{ t('md.submit.paramsTitle') }}</a-divider>

          <a-row :gutter="16">
            <a-col :xs="24" :md="12" :lg="8">
              <a-form-item :label="t('md.submit.forceField')" required>
                <a-select v-model:value="form.force_field" :options="forceFieldOptions" data-testid="md-force-field-select" />
              </a-form-item>
            </a-col>
            <a-col :xs="24" :md="12" :lg="8">
              <a-form-item :label="t('md.submit.durationNs')" required>
                <a-input-number
                  v-model:value="form.duration_ns"
                  :min="0.1"
                  :step="10"
                  :precision="1"
                  class="md-submit__number"
                  data-testid="md-duration-input"
                />
              </a-form-item>
            </a-col>
            <a-col :xs="24" :md="12" :lg="8">
              <a-form-item :label="t('md.submit.temperatureK')" required>
                <a-input-number
                  v-model:value="form.temperature_k"
                  :min="1"
                  :step="5"
                  :precision="0"
                  class="md-submit__number"
                  data-testid="md-temperature-input"
                />
              </a-form-item>
            </a-col>
            <a-col :xs="24" :md="12" :lg="8">
              <a-form-item :label="t('md.submit.pressureBar')" required>
                <a-input-number
                  v-model:value="form.pressure_bar"
                  :min="0.1"
                  :step="0.1"
                  :precision="2"
                  class="md-submit__number"
                  data-testid="md-pressure-input"
                />
              </a-form-item>
            </a-col>
            <a-col :xs="24" :md="12" :lg="8">
              <a-form-item :label="t('md.submit.seed')">
                <a-input-number
                  v-model:value="form.seed"
                  :min="0"
                  :precision="0"
                  class="md-submit__number"
                  data-testid="md-seed-input"
                />
              </a-form-item>
            </a-col>
          </a-row>

          <a-alert
            type="info"
            show-icon
            class="md-submit__estimate"
            :message="t('md.submit.estimateTitle')"
          >
            <template #description>
              <div data-testid="md-estimate">
                {{ t('md.submit.estimateValue', { hours: estimateText }) }}
              </div>
              <div class="md-submit__estimate-note">{{ t('md.submit.estimateDisclaimer') }}</div>
            </template>
          </a-alert>

          <div class="md-submit__actions">
            <a-button type="primary" :loading="submitting" :disabled="!canSubmit" @click="handleSubmit" data-testid="md-submit-btn">
              {{ submitting ? t('md.submit.submitting') : t('md.submit.submit') }}
            </a-button>
            <a-button :disabled="submitting" @click="resetForm">{{ t('md.submit.reset') }}</a-button>
          </div>
        </a-form>
      </a-spin>
    </a-card>
  </div>
</template>

<script setup lang="ts">
  import { computed, onMounted, reactive, ref, watch } from 'vue'
  import { useRouter } from 'vue-router'
  import { useI18n } from 'vue-i18n'
  import { message } from 'ant-design-vue'
  import AppPageHeader from '@/components/common/AppPageHeader.vue'
  import { listProjects } from '@/api/projects'
  import { getTarget, listStructures, listTargets } from '@/api/targets'
  import { findToolBySlug, MD_TOOL_SLUG, resolveToolVersionId, submitMdTask } from '@/api/md'
  import { estimateMdRuntimeHours } from './analysis'
  import type { ResearchProject } from '@/types/projects'
  import type { ProteinDetail, ProteinStructureDetail, TargetSummary } from '@/types/targets'
  import type { MdForceField, MdSubmitParams } from '@/types/md'

  const { t } = useI18n()
  const router = useRouter()

  const projects = ref<ResearchProject[]>([])
  const targets = ref<TargetSummary[]>([])
  const proteins = ref<ProteinDetail[]>([])
  const structures = ref<ProteinStructureDetail[]>([])

  const loadingProjects = ref(false)
  const loadingTargets = ref(false)
  const loadingProteins = ref(false)
  const loadingStructures = ref(false)
  const submitting = ref(false)

  const form = reactive<{
    projectId: string | undefined
    targetId: string | undefined
    proteinId: string | undefined
    structureId: string | undefined
    force_field: MdForceField
    duration_ns: number
    temperature_k: number
    pressure_bar: number
    seed: number | null
  }>({
    projectId: undefined,
    targetId: undefined,
    proteinId: undefined,
    structureId: undefined,
    force_field: 'amber99sb-ildn',
    duration_ns: 100,
    temperature_k: 300,
    pressure_bar: 1,
    seed: null
  })

  const projectOptions = computed(() => projects.value.map((project) => ({ value: project.id, label: project.name })))
  const targetOptions = computed(() => targets.value.map((target) => ({ value: target.id, label: target.name })))
  const proteinOptions = computed(() => proteins.value.map((protein) => ({ value: protein.id, label: protein.name })))
  const structureOptions = computed(() =>
    structures.value.map((structure, index) => ({
      value: structure.id,
      label: `#${index + 1}${structure.prepared_file_id ? ` ${t('md.submit.prepared')}` : ''}`
    }))
  )
  const forceFieldOptions = computed(() => [
    { value: 'amber99sb-ildn', label: t('md.submit.forceFieldAmber') },
    { value: 'charmm36', label: t('md.submit.forceFieldCharmm') }
  ])

  const selectedStructure = computed(
    () => structures.value.find((structure) => structure.id === form.structureId) ?? null
  )

  const complexFileId = computed(() => {
    const structure = selectedStructure.value
    if (!structure) return null
    return structure.prepared_file_id ?? structure.structure_file_id ?? null
  })

  const canSubmit = computed(() => Boolean(form.projectId && complexFileId.value && form.duration_ns > 0))

  const estimateHours = computed(() =>
    estimateMdRuntimeHours({ durationNs: Number(form.duration_ns) || 0, gpuCount: 1 })
  )
  const estimateText = computed(() =>
    Number.isFinite(estimateHours.value) ? `${estimateHours.value}` : '-'
  )

  function errorMessage(error: unknown, fallback: string): string {
    if (error instanceof Error && error.message) return error.message
    return fallback
  }

  async function loadProjects(): Promise<void> {
    loadingProjects.value = true
    try {
      projects.value = (await listProjects()).data.items
    } catch (error) {
      message.error(errorMessage(error, t('md.common.loadFailed')))
    } finally {
      loadingProjects.value = false
    }
  }

  async function loadTargets(projectId: string): Promise<void> {
    loadingTargets.value = true
    targets.value = []
    try {
      targets.value = (await listTargets(projectId)).data.items
    } catch (error) {
      message.error(errorMessage(error, t('md.common.loadFailed')))
    } finally {
      loadingTargets.value = false
    }
  }

  async function loadProteins(targetId: string): Promise<void> {
    loadingProteins.value = true
    proteins.value = []
    try {
      const target = (await getTarget(targetId)).data
      proteins.value = target.proteins ?? []
    } catch (error) {
      message.error(errorMessage(error, t('md.common.loadFailed')))
    } finally {
      loadingProteins.value = false
    }
  }

  async function loadStructures(proteinId: string): Promise<void> {
    loadingStructures.value = true
    structures.value = []
    try {
      structures.value = (await listStructures(proteinId)).data.items
    } catch (error) {
      message.error(errorMessage(error, t('md.common.loadFailed')))
    } finally {
      loadingStructures.value = false
    }
  }

  watch(
    () => form.projectId,
    (projectId) => {
      form.targetId = undefined
      form.proteinId = undefined
      form.structureId = undefined
      targets.value = []
      proteins.value = []
      structures.value = []
      if (projectId) void loadTargets(projectId)
    }
  )

  watch(
    () => form.targetId,
    (targetId) => {
      form.proteinId = undefined
      form.structureId = undefined
      proteins.value = []
      structures.value = []
      if (targetId) void loadProteins(targetId)
    }
  )

  watch(
    () => form.proteinId,
    (proteinId) => {
      form.structureId = undefined
      structures.value = []
      if (proteinId) void loadStructures(proteinId)
    }
  )

  function resetForm(): void {
    form.targetId = undefined
    form.proteinId = undefined
    form.structureId = undefined
    form.force_field = 'amber99sb-ildn'
    form.duration_ns = 100
    form.temperature_k = 300
    form.pressure_bar = 1
    form.seed = null
    targets.value = []
    proteins.value = []
    structures.value = []
  }

  async function handleSubmit(): Promise<void> {
    if (!form.projectId) {
      message.warning(t('md.submit.projectRequired'))
      return
    }
    if (!complexFileId.value) {
      message.warning(t('md.submit.structureRequired'))
      return
    }
    submitting.value = true
    try {
      const tool = await findToolBySlug(MD_TOOL_SLUG)
      if (!tool) {
        message.error(t('md.submit.toolMissing', { slug: MD_TOOL_SLUG }))
        return
      }
      const toolVersionId = await resolveToolVersionId(tool)
      const params: MdSubmitParams = {
        force_field: form.force_field,
        duration_ns: Number(form.duration_ns),
        temperature_k: Number(form.temperature_k),
        pressure_bar: Number(form.pressure_bar)
      }
      if (form.seed !== null && form.seed !== undefined) {
        params.seed = Number(form.seed)
      }
      const taskId = await submitMdTask({
        projectId: form.projectId,
        toolId: tool.id,
        toolVersionId,
        params,
        complexFileId: complexFileId.value,
        name: `MD ${params.duration_ns}ns`
      })
      message.success(t('md.submit.submitSuccess'))
      await router.push(`/tasks/${taskId}/md`)
    } catch (error) {
      message.error(errorMessage(error, t('md.submit.submitFailed')))
    } finally {
      submitting.value = false
    }
  }

  onMounted(() => {
    void loadProjects()
  })
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .md-submit {
    max-width: @container-xl;
    margin: 0 auto;
  }

  .md-submit__card {
    border-radius: @border-radius-lg;
  }

  .md-submit__number {
    width: 100%;
  }

  .md-submit__structure {
    display: flex;
    align-items: center;
    gap: @spacing-sm;
    margin-bottom: @spacing-xs;
  }

  .md-submit__structure-id {
    color: @text-color-light-secondary;
    font-family: @font-family-mono;
    font-size: @font-size-sm;
  }

  .md-submit__structure-src {
    color: @text-color-light-secondary;
    font-size: @font-size-sm;
  }

  .md-submit__hint {
    margin: 0 0 @spacing-md;
    color: @text-color-light-secondary;
    font-size: @font-size-sm;
  }

  .md-submit__estimate {
    margin: @spacing-md 0;
  }

  .md-submit__estimate-note {
    margin-top: @spacing-xs;
    color: @text-color-light-secondary;
    font-size: @font-size-xs;
  }

  .md-submit__actions {
    display: flex;
    gap: @spacing-sm;
    margin-top: @spacing-lg;
  }
</style>
