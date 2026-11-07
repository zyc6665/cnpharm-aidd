<template>
  <div class="md-submit" data-testid="md-submit-page">
    <app-page-header :title="t('md.submit.title')" :subtitle="t('md.submit.subtitle')" />

    <a-card :bordered="false" class="md-submit__card">
      <div class="md-submit__model">
        <div class="md-submit__model-label">{{ t('design.modelSelect.label') }}</div>
        <ModelSelect v-model="selectedSlug" :options="modelOptions" :loading="modelLoading" />
      </div>
    </a-card>

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
              <a-form-item :label="t('md.submit.nsteps')" required>
                <a-input-number
                  v-model:value="form.nsteps"
                  :min="0"
                  :max="500000"
                  :step="100"
                  :precision="0"
                  class="md-submit__number"
                  data-testid="md-nsteps-input"
                />
              </a-form-item>
            </a-col>
            <a-col :xs="24" :md="12" :lg="8">
              <a-form-item :label="t('md.submit.dt')" required>
                <a-input-number
                  v-model:value="form.dt"
                  :min="0.001"
                  :max="0.004"
                  :step="0.001"
                  :precision="3"
                  class="md-submit__number"
                  data-testid="md-dt-input"
                />
              </a-form-item>
            </a-col>
            <a-col :xs="24" :md="12" :lg="8">
              <a-form-item :label="t('md.submit.temperature')" required>
                <a-input-number
                  v-model:value="form.temperature"
                  :min="250"
                  :max="400"
                  :step="5"
                  :precision="0"
                  class="md-submit__number"
                  data-testid="md-temperature-input"
                />
              </a-form-item>
            </a-col>
            <a-col :xs="24" :md="12" :lg="8">
              <a-form-item :label="t('md.submit.boxDistance')" required>
                <a-input-number
                  v-model:value="form.box_distance"
                  :min="0.8"
                  :max="2.5"
                  :step="0.1"
                  :precision="2"
                  class="md-submit__number"
                  data-testid="md-box-distance-input"
                />
              </a-form-item>
            </a-col>
            <a-col :xs="24" :md="12" :lg="8">
              <a-form-item :label="t('md.submit.waterModel')">
                <a-select v-model:value="form.water_model" :options="waterModelOptions" data-testid="md-water-model-select" />
              </a-form-item>
            </a-col>
            <a-col :xs="24" :md="12" :lg="8">
              <a-form-item :label="t('md.submit.device')">
                <a-select v-model:value="form.device" :options="deviceOptions" data-testid="md-device-select" />
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
  import ModelSelect from '@/components/design/ModelSelect.vue'
  import { useModelOptions } from '@/composables/useModelOptions'
  import { estimateMdRuntimeHours } from './analysis'
  import type { ResearchProject } from '@/types/projects'
  import type { ProteinDetail, ProteinStructureDetail, TargetSummary } from '@/types/targets'
  import type { MdSubmitParams } from '@/types/md'

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

  // 同类 MD 模型可自由选择；默认 gromacs。
  const {
    options: modelOptions,
    selectedSlug,
    loading: modelLoading,
    load: loadModels
  } = useModelOptions('molecular_dynamics', { defaultSlug: MD_TOOL_SLUG })

  const form = reactive<{
    projectId: string | undefined
    targetId: string | undefined
    proteinId: string | undefined
    structureId: string | undefined
    nsteps: number
    dt: number
    temperature: number
    box_distance: number
    water_model: string
    device: 'auto' | 'cpu' | 'gpu'
  }>({
    projectId: undefined,
    targetId: undefined,
    proteinId: undefined,
    structureId: undefined,
    nsteps: 2500,
    dt: 0.002,
    temperature: 300,
    box_distance: 1.0,
    water_model: 'tip3p',
    device: 'auto'
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
  const waterModelOptions = computed(() => [
    { value: 'tip3p', label: 'TIP3P' },
    { value: 'spc', label: 'SPC' },
    { value: 'tip4p', label: 'TIP4P' }
  ])
  const deviceOptions = computed(() => [
    { value: 'auto', label: t('md.submit.deviceAuto') },
    { value: 'cpu', label: 'CPU' },
    { value: 'gpu', label: 'GPU' }
  ])

  const selectedStructure = computed(
    () => structures.value.find((structure) => structure.id === form.structureId) ?? null
  )

  const complexFileId = computed(() => {
    const structure = selectedStructure.value
    if (!structure) return null
    return structure.prepared_file_id ?? structure.structure_file_id ?? null
  })

  const durationNs = computed(() => (Number(form.nsteps) * Number(form.dt)) / 1000)

  const canSubmit = computed(
    () =>
      Boolean(form.projectId && complexFileId.value) &&
      Number(form.nsteps) > 0 &&
      Number(form.dt) >= 0.001 &&
      Number(form.dt) <= 0.004
  )

  const estimateHours = computed(() =>
    estimateMdRuntimeHours({ durationNs: Number(durationNs.value) || 0, gpuCount: 1 })
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
    form.nsteps = 2500
    form.dt = 0.002
    form.temperature = 300
    form.box_distance = 1.0
    form.water_model = 'tip3p'
    form.device = 'auto'
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
      const tool = await findToolBySlug(selectedSlug.value)
      if (!tool) {
        message.error(t('md.submit.toolMissing', { slug: selectedSlug.value }))
        return
      }
      const toolVersionId = await resolveToolVersionId(tool)
      const params: MdSubmitParams = {
        nsteps: Number(form.nsteps),
        dt: Number(form.dt),
        temperature: Number(form.temperature),
        box_distance: Number(form.box_distance),
        water_model: form.water_model,
        device: form.device
      }
      const taskId = await submitMdTask({
        projectId: form.projectId,
        toolId: tool.id,
        toolVersionId,
        params,
        complexFileId: complexFileId.value,
        name: `MD ${durationNs.value.toFixed(2)}ns`
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
    void loadModels()
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
