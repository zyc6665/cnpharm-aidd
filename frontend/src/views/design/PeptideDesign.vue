<template>
  <main class="design-page" data-testid="peptide-design-page">
    <AppPageHeader :title="t('design.peptide.title')" :subtitle="t('design.peptide.subtitle')" />

    <a-spin :spinning="resolving">
      <a-alert
        v-if="toolError"
        type="error"
        show-icon
        :message="t('design.peptide.toolMissing')"
        data-testid="peptide-tool-error"
      />

      <section class="design-section">
        <h3 class="design-section__title">{{ t('design.modelSelect.label') }}</h3>
        <ModelSelect v-model="selectedSlug" :options="modelOptions" :loading="modelLoading" />
      </section>

      <section class="design-section">
        <h3 class="design-section__title">{{ t('design.peptide.project') }}</h3>
        <a-select
          v-model:value="projectId"
          :options="projectOptions"
          :placeholder="t('design.peptide.projectPlaceholder')"
          show-search
          option-filter-prop="label"
          data-testid="peptide-project"
        />
      </section>

      <section class="design-section">
        <h3 class="design-section__title">{{ t('design.peptide.sequenceSource') }}</h3>
        <a-radio-group
          v-model:value="sequenceSource"
          button-style="solid"
          data-testid="peptide-sequence-source"
        >
          <a-radio-button value="manual">{{ t('design.peptide.sourceManual') }}</a-radio-button>
          <a-radio-button value="target">{{ t('design.peptide.sourceTarget') }}</a-radio-button>
        </a-radio-group>
        <div v-if="sequenceSource === 'target'" class="sequence-source" data-testid="peptide-target-source">
          <a-select
            v-model:value="selectedTargetId"
            :options="targetOptions"
            :loading="targetsLoading"
            :placeholder="t('design.peptide.targetPlaceholder')"
            :not-found-content="t('design.peptide.noTargets')"
            show-search
            option-filter-prop="label"
            data-testid="peptide-target-select"
            @change="handleTargetChange"
          />
          <a-select
            v-model:value="selectedProteinId"
            :options="proteinOptions"
            :loading="proteinsLoading"
            :disabled="!selectedTargetId"
            :placeholder="t('design.peptide.proteinPlaceholder')"
            :not-found-content="t('design.peptide.noProteins')"
            show-search
            option-filter-prop="label"
            data-testid="peptide-protein-select"
            @change="handleProteinChange"
          />
          <p class="field-hint">{{ t('design.peptide.targetSequenceHint') }}</p>
        </div>
      </section>

      <section class="design-section">
        <h3 class="design-section__title">{{ t('design.section.parameters') }}</h3>
        <ModelParameterForm
          v-if="selectedOption?.parameterSchema"
          v-model="form.params"
          :schema="selectedOption.parameterSchema"
          :disabled="submitting"
        />
      </section>

      <div class="design-actions">
        <a-button
          type="primary"
          :loading="submitting"
          :disabled="!canSubmit"
          data-testid="peptide-submit"
          @click="handleSubmit"
        >
          {{ t('design.peptide.submit') }}
        </a-button>
      </div>
    </a-spin>
  </main>
</template>

<script setup lang="ts">
  import { computed, onMounted, reactive, ref, watch } from 'vue'
  import { useRoute, useRouter } from 'vue-router'
  import { message } from 'ant-design-vue'
  import { useI18n } from 'vue-i18n'
  import AppPageHeader from '@/components/common/AppPageHeader.vue'
  import ModelSelect from '@/components/design/ModelSelect.vue'
  import ModelParameterForm from '@/components/design/ModelParameterForm.vue'
  import { useModelOptions } from '@/composables/useModelOptions'
  import { listDesignProjects, resolveToolBySlug, submitDesignTask } from '@/api/design'
  import { getTarget, listTargets } from '@/api/targets'
  import {
    buildDefaultValues,
    normalizeParameters,
    validateParameters,
    type ParameterValues
  } from '@/domain/tools/parameterSchema'
  import type { ResearchProject } from '@/types/projects'
  import type { ProteinDetail } from '@/types/targets'
  import type { ResolvedDesignTool } from '@/types/design'
  import { PEPTIDE_DESIGN_TOOL_SLUG } from '@/types/design'

  const router = useRouter()
  const route = useRoute()
  const { t } = useI18n()

  const props = withDefaults(defineProps<{ initialProjectId?: string }>(), {
    initialProjectId: ''
  })

  const resolving = ref(false)
  const submitting = ref(false)
  const toolError = ref(false)
  const resolvedTool = ref<ResolvedDesignTool | null>(null)
  const projects = ref<ResearchProject[]>([])
  const projectId = ref(
    props.initialProjectId ||
      (typeof route.query.project_id === 'string' ? route.query.project_id : '')
  )

  const {
    options: modelOptions,
    selectedSlug,
    selectedOption,
    loading: modelLoading,
    load: loadModels
  } = useModelOptions('peptide_design', { defaultSlug: PEPTIDE_DESIGN_TOOL_SLUG })

  const form = reactive<{ params: ParameterValues }>({ params: {} })

  /**
   * 序列来源：手填 or 复用项目里已有的靶点序列。
   * 多肽设计真正需要的输入只有一条序列，能复用就不要再让人复制粘贴一遍。
   */
  const sequenceSource = ref<'manual' | 'target'>('manual')
  const targets = ref<{ id: string; name: string }[]>([])
  const proteins = ref<ProteinDetail[]>([])
  const selectedTargetId = ref('')
  const selectedProteinId = ref('')
  const targetsLoading = ref(false)
  const proteinsLoading = ref(false)

  const targetOptions = computed(() => targets.value.map(item => ({ value: item.id, label: item.name })))
  const proteinOptions = computed(() =>
    proteins.value.map(item => ({
      value: item.id,
      label: `${item.name}${item.seq_length ? ` · ${item.seq_length} aa` : ''}`
    }))
  )

  const projectOptions = computed(() =>
    projects.value.map(project => ({ value: project.id, label: project.name }))
  )

  const sequenceLength = computed(() => String(form.params.sequence ?? '').replace(/\s/g, '').length)
  const canSubmit = computed(
    () =>
      Boolean(resolvedTool.value && projectId.value) &&
      sequenceLength.value >= 4 &&
      sequenceLength.value <= 20000 &&
      validateParameters(selectedOption.value?.parameterSchema ?? null, form.params).length === 0
  )

  async function loadProjects(): Promise<void> {
    try {
      projects.value = await listDesignProjects()
      if (!projectId.value && projects.value.length > 0) {
        projectId.value = projects.value[0]?.id ?? ''
      }
    } catch {
      projects.value = []
    }
  }

  async function loadTargets(): Promise<void> {
    if (!projectId.value) {
      targets.value = []
      return
    }
    targetsLoading.value = true
    try {
      const response = await listTargets(projectId.value, { page: 1, page_size: 100 })
      targets.value = (response.data.items ?? []).map(item => ({ id: item.id, name: item.name }))
    } catch {
      targets.value = []
    } finally {
      targetsLoading.value = false
    }
  }

  async function handleTargetChange(value: unknown): Promise<void> {
    selectedTargetId.value = typeof value === 'string' ? value : ''
    selectedProteinId.value = ''
    proteins.value = []
    if (!selectedTargetId.value) return
    proteinsLoading.value = true
    try {
      const response = await getTarget(selectedTargetId.value)
      proteins.value = response.data.proteins ?? []
    } catch {
      proteins.value = []
    } finally {
      proteinsLoading.value = false
    }
  }

  function handleProteinChange(value: unknown): void {
    selectedProteinId.value = typeof value === 'string' ? value : ''
    const protein = proteins.value.find(item => item.id === selectedProteinId.value)
    if (protein?.sequence) {
      form.params.sequence = protein.sequence
      message.success(t('design.peptide.sequenceFilled'))
    }
  }

  async function loadTool(): Promise<void> {
    resolving.value = true
    toolError.value = false
    try {
      resolvedTool.value = await resolveToolBySlug(selectedSlug.value)
      toolError.value = !resolvedTool.value
    } catch {
      toolError.value = true
    } finally {
      resolving.value = false
    }
  }

  function validate(): string | null {
    if (!projectId.value) return t('design.peptide.projectRequired')
    if (sequenceLength.value < 4) return t('design.peptide.sequenceTooShort')
    if (sequenceLength.value > 20000) return t('design.peptide.sequenceTooLong')
    const errors = validateParameters(selectedOption.value?.parameterSchema ?? null, form.params)
    if (errors.length > 0) return t('design.peptide.invalidBatchSize')
    return null
  }

  async function handleSubmit(): Promise<void> {
    if (!resolvedTool.value) {
      message.warning(t('design.peptide.toolMissing'))
      return
    }
    const invalid = validate()
    if (invalid) {
      message.warning(invalid)
      return
    }
    submitting.value = true
    try {
      const response = await submitDesignTask({
        name: t('design.peptide.taskName'),
        projectId: projectId.value,
        toolId: resolvedTool.value.tool.id,
        toolVersionId: resolvedTool.value.version.id,
        params: normalizeParameters(selectedOption.value?.parameterSchema ?? null, form.params)
      })
      message.success(t('design.peptide.submitted'))
      await router.push({ name: 'GenerationResults', params: { id: response.data.id } })
    } catch {
      message.error(t('design.peptide.failed'))
    } finally {
      submitting.value = false
    }
  }

  watch(
    selectedOption,
    option => {
      form.params = buildDefaultValues(option?.parameterSchema ?? null)
    },
    { immediate: true }
  )

  onMounted(() => {
    void loadProjects()
    void loadModels().then(() => loadTool())
  })

  watch(selectedSlug, () => {
    void loadTool()
  })

  watch([projectId, sequenceSource], ([currentProject, source]) => {
    if (source === 'target' && currentProject) void loadTargets()
  })
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .sequence-source {
    display: grid;
    gap: 12px;
    margin-top: 12px;
  }

  .field-hint {
    margin: 0;
    color: var(--color-text-secondary, #8c8c8c);
    font-size: 12px;
  }

  .design-page {
    max-width: 960px;
    margin: 0 auto;
    padding: 32px 24px 48px;
  }

  .design-section {
    margin-bottom: 24px;
    padding: 20px;
    border: 1px solid @border-color;
    border-radius: 8px;
    background: @bg-surface;
  }

  .design-section__title {
    margin: 0 0 16px;
    font-size: 16px;
    font-weight: 600;
  }

  .number-input {
    width: 100%;
  }

  .design-actions {
    display: flex;
    justify-content: flex-end;
  }
</style>
