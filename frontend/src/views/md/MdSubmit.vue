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
                  @change="handleProjectChange"
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
                  @change="handleTargetChange"
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
                  @change="handleProteinChange"
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

          <a-form-item :label="t('md.submit.ligandUploadLabel')">
            <div class="md-submit__ligand-row">
              <a-upload
                :before-upload="handleLigandBeforeUpload"
                :show-upload-list="false"
                accept=".sdf,.mol,.mol2,.pdb"
                :disabled="submitting || uploadingLigand"
              >
                <a-button :loading="uploadingLigand" :disabled="submitting" data-testid="md-ligand-upload-btn">
                  {{ t('md.submit.ligandUploadButton') }}
                </a-button>
              </a-upload>
              <a-tag v-if="ligandFileId" color="blue" data-testid="md-ligand-tag">
                {{ t('md.submit.ligandUploadedTag', { name: ligandFilename }) }}
              </a-tag>
              <a-button
                v-if="ligandFileId"
                type="link"
                size="small"
                :disabled="submitting"
                @click="clearLigand"
                data-testid="md-ligand-clear-btn"
              >
                {{ t('md.submit.ligandClear') }}
              </a-button>
            </div>
            <p class="md-submit__hint md-submit__ligand-hint">{{ t('md.submit.ligandUploadHint') }}</p>
          </a-form-item>

          <a-divider orientation="left">{{ t('md.submit.paramsTitle') }}</a-divider>

          <ModelParameterForm
            v-if="selectedOption?.parameterSchema"
            v-model="params"
            :schema="selectedOption.parameterSchema"
            :disabled="submitting"
          />

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
  import { useRoute, useRouter } from 'vue-router'
  import { useRequestSequence } from '@/composables/useRequestSequence'
  import { useI18n } from 'vue-i18n'
  import { message } from 'ant-design-vue'
  import AppPageHeader from '@/components/common/AppPageHeader.vue'
  import { listProjects } from '@/api/projects'
  import { uploadFile } from '@/api/files'
  import { getProtein, getStructure, getTarget, listStructures, listTargets } from '@/api/targets'
  import { findToolBySlug, MD_TOOL_SLUG, resolveToolVersionId, submitMdTask } from '@/api/md'
  import ModelSelect from '@/components/design/ModelSelect.vue'
  import ModelParameterForm from '@/components/design/ModelParameterForm.vue'
  import { useModelOptions } from '@/composables/useModelOptions'
  import {
    buildDefaultValues,
    normalizeParameters,
    validateParameters,
    type ParameterValues
  } from '@/domain/tools/parameterSchema'
  import { estimateMdRuntimeHours } from './analysis'
  import type { ResearchProject } from '@/types/projects'
  import type { ProteinDetail, ProteinStructureDetail, TargetSummary } from '@/types/targets'
  import type { MdSubmitParams } from '@/types/md'

  const { t } = useI18n()
  const router = useRouter()
  const route = useRoute()
  const targetsSequence = useRequestSequence()
  const proteinsSequence = useRequestSequence()
  const structuresSequence = useRequestSequence()
  const prefillSequence = useRequestSequence()
  let applyingPrefillProject = false
  const queryValue = (key: string): string | undefined => {
    const value = route.query[key]
    return typeof value === 'string' && value.trim() ? value : undefined
  }

  const projects = ref<ResearchProject[]>([])
  const targets = ref<TargetSummary[]>([])
  const proteins = ref<ProteinDetail[]>([])
  const structures = ref<ProteinStructureDetail[]>([])

  const loadingProjects = ref(false)
  const loadingTargets = ref(false)
  const loadingProteins = ref(false)
  const loadingStructures = ref(false)
  const submitting = ref(false)
  const uploadingLigand = ref(false)
  const ligandFileId = ref<string | null>(null)
  const ligandFilename = ref('')

  // 同类 MD 模型可自由选择；默认 gromacs；参数 schema 随模型切换。
  const {
    options: modelOptions,
    selectedSlug,
    selectedOption,
    loading: modelLoading,
    load: loadModels
  } = useModelOptions('molecular_dynamics', { defaultSlug: MD_TOOL_SLUG })

  const form = reactive<{
    projectId: string | undefined
    targetId: string | undefined
    proteinId: string | undefined
    structureId: string | undefined
  }>({
    projectId: undefined,
    targetId: undefined,
    proteinId: undefined,
    structureId: undefined
  })
  const params = ref<ParameterValues>({})

  const projectOptions = computed(() => projects.value.map((project) => ({ value: project.id, label: project.name })))
  const targetOptions = computed(() => targets.value.map((target) => ({ value: target.id, label: target.name })))
  const proteinOptions = computed(() => proteins.value.map((protein) => ({ value: protein.id, label: protein.name })))
  const structureOptions = computed(() =>
    structures.value.map((structure, index) => ({
      value: structure.id,
      label: `#${index + 1}${structure.prepared_file_id ? ` ${t('md.submit.prepared')}` : ''}`
    }))
  )
  const selectedStructure = computed(
    () => structures.value.find((structure) => structure.id === form.structureId) ?? null
  )

  const complexFileId = computed(() => {
    const structure = selectedStructure.value
    if (!structure) return null
    return structure.prepared_file_id ?? structure.structure_file_id ?? null
  })

  const durationNs = computed(
    () => (Number(params.value.nsteps ?? 0) * Number(params.value.dt ?? 0)) / 1000
  )

  const canSubmit = computed(
    () =>
      Boolean(form.projectId && complexFileId.value) &&
      validateParameters(selectedOption.value?.parameterSchema ?? null, params.value).length === 0
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
    let loaded = false
    try {
      projects.value = (await listProjects()).data.items
      loaded = true
    } catch (error) {
      message.error(errorMessage(error, t('md.common.loadFailed')))
    } finally {
      loadingProjects.value = false
    }
    if (loaded) await applyQueryPrefill()
  }

  async function loadTargets(projectId: string): Promise<void> {
    const seq = targetsSequence.next()
    loadingTargets.value = true
    targets.value = []
    try {
      const items = (await listTargets(projectId)).data.items
      if (targetsSequence.isCurrent(seq) && form.projectId === projectId) targets.value = items
    } catch (error) {
      if (targetsSequence.isCurrent(seq) && form.projectId === projectId) message.error(errorMessage(error, t('md.common.loadFailed')))
    } finally {
      if (targetsSequence.isCurrent(seq) && form.projectId === projectId) loadingTargets.value = false
    }
  }

  async function loadProteins(targetId: string): Promise<void> {
    const seq = proteinsSequence.next()
    loadingProteins.value = true
    proteins.value = []
    try {
      const target = (await getTarget(targetId)).data
      if (proteinsSequence.isCurrent(seq) && form.targetId === targetId) proteins.value = target.proteins ?? []
    } catch (error) {
      if (proteinsSequence.isCurrent(seq) && form.targetId === targetId) message.error(errorMessage(error, t('md.common.loadFailed')))
    } finally {
      if (proteinsSequence.isCurrent(seq) && form.targetId === targetId) loadingProteins.value = false
    }
  }

  async function loadStructures(proteinId: string): Promise<void> {
    const seq = structuresSequence.next()
    loadingStructures.value = true
    structures.value = []
    try {
      const items = (await listStructures(proteinId)).data.items
      if (structuresSequence.isCurrent(seq) && form.proteinId === proteinId) structures.value = items
    } catch (error) {
      if (structuresSequence.isCurrent(seq) && form.proteinId === proteinId) message.error(errorMessage(error, t('md.common.loadFailed')))
    } finally {
      if (structuresSequence.isCurrent(seq) && form.proteinId === proteinId) loadingStructures.value = false
    }
  }

  function handleProjectChange(): void {
    prefillSequence.invalidate()
    clearProjectDescendants()
    if (form.projectId) void loadTargets(form.projectId)
  }

  function clearProjectDescendants(): void {
    targetsSequence.invalidate()
    proteinsSequence.invalidate()
    structuresSequence.invalidate()
    form.targetId = undefined
    form.proteinId = undefined
    form.structureId = undefined
    targets.value = []
    proteins.value = []
    structures.value = []
    loadingTargets.value = false
    loadingProteins.value = false
    loadingStructures.value = false
  }

  function handleTargetChange(): void {
    proteinsSequence.invalidate()
    structuresSequence.invalidate()
    form.proteinId = undefined
    form.structureId = undefined
    proteins.value = []
    structures.value = []
    loadingProteins.value = false
    loadingStructures.value = false
    if (form.targetId) void loadProteins(form.targetId)
  }

  function handleProteinChange(): void {
    structuresSequence.invalidate()
    form.structureId = undefined
    structures.value = []
    loadingStructures.value = false
    if (form.proteinId) void loadStructures(form.proteinId)
  }

  async function applyQueryPrefill(): Promise<void> {
    const seq = prefillSequence.next()
    const query = { project: queryValue('project_id'), target: queryValue('target_id'), protein: queryValue('protein_id'), structure: queryValue('structure_id') }
    if (!query.project) return
    const current = () => prefillSequence.isCurrent(seq) && route.query.project_id === query.project
    const warn = () => message.warning(t('md.submit.prefillMismatch'))
    if (!projects.value.some(item => item.id === query.project)) { warn(); return }
    applyingPrefillProject = true
    form.projectId = query.project
    applyingPrefillProject = false
    await loadTargets(query.project)
    if (!current()) return
    let targetId = query.target
    let proteinId = query.protein
    const structureId = query.structure
    if (structureId) {
      try {
        const structure = (await getStructure(structureId)).data
        if (!current()) return
        if (proteinId && proteinId !== structure.protein_id) { warn(); return }
        proteinId = structure.protein_id
        const protein = (await getProtein(proteinId)).data
        if (!current()) return
        if (targetId && targetId !== protein.target_id) { warn(); return }
        targetId = protein.target_id
        const target = (await getTarget(targetId)).data
        if (!current()) return
        if (target.project_id !== query.project) { warn(); return }
        if (!targets.value.some(item => item.id === targetId)) { warn(); return }
        form.targetId = targetId
        await loadProteins(targetId)
        if (!current()) return
        if (!proteins.value.some(item => item.id === proteinId)) { warn(); return }
        form.proteinId = proteinId
        await loadStructures(proteinId)
        if (!current()) return
        if (!structures.value.some(item => item.id === structureId)) { warn(); return }
        form.structureId = structureId
        return
      } catch { if (current()) warn(); return }
    }
    if (targetId && targets.value.some(item => item.id === targetId)) {
      form.targetId = targetId
      await loadProteins(targetId)
      if (!current()) return
      if (proteinId && proteins.value.some(item => item.id === proteinId)) {
        form.proteinId = proteinId
        await loadStructures(proteinId)
        if (!current()) return
        if (query.structure && structures.value.some(item => item.id === query.structure)) form.structureId = query.structure
        else if (query.structure) warn()
      } else if (proteinId) warn()
    } else if (targetId) warn()
  }

  watch(() => [route.query.project_id, route.query.target_id, route.query.protein_id, route.query.structure_id], () => void applyQueryPrefill())

  function clearLigand(): void {
    ligandFileId.value = null
    ligandFilename.value = ''
  }

  async function handleLigandBeforeUpload(file: File): Promise<boolean> {
    uploadingLigand.value = true
    try {
      const response = await uploadFile(file)
      ligandFileId.value = response.data.id
      ligandFilename.value = file.name
      message.success(t('md.submit.ligandUploadSuccess'))
    } catch (error) {
      message.error(errorMessage(error, t('md.submit.ligandUploadFailed')))
    } finally {
      uploadingLigand.value = false
    }
    return false
  }

  function resetForm(): void {
    prefillSequence.invalidate()
    form.targetId = undefined
    form.proteinId = undefined
    form.structureId = undefined
    clearLigand()
    params.value = buildDefaultValues(selectedOption.value?.parameterSchema ?? null)
    targets.value = []
    proteins.value = []
    structures.value = []
    if (form.projectId) void loadTargets(form.projectId)
  }

  async function handleSubmit(): Promise<void> {
    if (submitting.value) return
    if (!form.projectId) {
      message.warning(t('md.submit.projectRequired'))
      return
    }
    const structure = selectedStructure.value
    const fileId = structure?.prepared_file_id ?? structure?.structure_file_id ?? null
    if (!fileId) {
      message.warning(t('md.submit.structureRequired'))
      return
    }
    const tool = selectedOption.value
    const schema = tool?.parameterSchema ?? null
    const params2 = normalizeParameters(schema, params.value) as unknown as MdSubmitParams
    if (validateParameters(schema, params.value).length > 0) return
    submitting.value = true
    const snapshot = {
      projectId: form.projectId,
      toolSlug: selectedSlug.value,
      params: params2,
      complexFileId: fileId,
      name: `MD ${durationNs.value.toFixed(2)}ns`
    }
    try {
      const resolved = await findToolBySlug(snapshot.toolSlug)
      if (!resolved) {
        message.error(t('md.submit.toolMissing', { slug: snapshot.toolSlug }))
        return
      }
      const toolVersionId = await resolveToolVersionId(resolved)
      const taskId = await submitMdTask({
        projectId: snapshot.projectId,
        toolId: resolved.id,
        toolVersionId,
        params: snapshot.params,
        complexFileId: snapshot.complexFileId,
        ligandFileId: ligandFileId.value,
        name: snapshot.name
      })
      message.success(t('md.submit.submitSuccess'))
      await router.push(`/tasks/${taskId}/md`)
    } catch (error) {
      message.error(errorMessage(error, t('md.submit.submitFailed')))
    } finally {
      submitting.value = false
    }
  }

  watch(
    selectedOption,
    option => {
      params.value = buildDefaultValues(option?.parameterSchema ?? null)
    },
    { immediate: true }
  )

  onMounted(() => {
    void loadModels()
    void loadProjects()
  })
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .md-submit {
    max-width: @page-max-width;
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

  .md-submit__ligand-row {
    display: flex;
    align-items: center;
    flex-wrap: wrap;
    gap: @spacing-sm;
  }

  .md-submit__ligand-hint {
    margin: @spacing-xs 0 0;
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
