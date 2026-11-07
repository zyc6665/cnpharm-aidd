<template>
  <main class="design-page" data-testid="molecule-generation-page">
    <AppPageHeader :title="t('design.molecule.title')" :subtitle="t('design.molecule.subtitle')" />

    <a-spin :spinning="resolving">
      <a-alert
        v-if="toolError"
        type="error"
        show-icon
        :message="t('design.molecule.toolMissing')"
        data-testid="molecule-tool-error"
      />

      <section class="design-section">
        <h3 class="design-section__title">{{ t('design.modelSelect.label') }}</h3>
        <ModelSelect v-model="selectedSlug" :options="modelOptions" :loading="modelLoading" />
      </section>

      <section class="design-section">
        <h3 class="design-section__title">{{ t('design.section.inputs') }}</h3>
        <PocketPicker v-model="pocketSelection" :default-project-id="defaultProjectId" />
      </section>

      <a-alert
        v-if="pocketSelection && !pocketSelection.structureFileId"
        type="warning"
        show-icon
        :message="t('design.molecule.pocketMissingFile')"
        class="pocket-alert"
      />
      <a-alert
        v-else-if="pocketSelection && !hasCenter"
        type="warning"
        show-icon
        :message="t('design.molecule.pocketMissingCenter')"
        class="pocket-alert"
      />

      <section v-if="pocketSelection" class="design-section pocket-summary" data-testid="molecule-pocket-summary">
        <h3 class="design-section__title">{{ t('design.molecule.pocketSummary') }}</h3>
        <a-descriptions :column="3" size="small" bordered>
          <a-descriptions-item :label="t('design.molecule.pocketLabel')">
            {{ pocketSelection.pocketLabel || '-' }}
          </a-descriptions-item>
          <a-descriptions-item :label="t('design.molecule.pocketCenter')">
            {{ centerText }}
          </a-descriptions-item>
          <a-descriptions-item :label="t('design.molecule.pocketBox')">
            {{ boxText }}
          </a-descriptions-item>
        </a-descriptions>
      </section>

      <section class="design-section">
        <h3 class="design-section__title">{{ t('design.section.parameters') }}</h3>
        <ModelParameterForm
          v-if="selectedOption?.parameterSchema"
          v-model="form.params"
          :schema="selectedOption.parameterSchema"
          :overrides="hiddenParams"
          :disabled="submitting"
        />
        <p class="param-hint">{{ t('design.molecule.paramHint') }}</p>
      </section>

      <div class="design-actions">
        <a-button
          type="primary"
          :loading="submitting"
          :disabled="!canSubmit"
          data-testid="molecule-submit"
          @click="handleSubmit"
        >
          {{ t('design.molecule.submit') }}
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
  import PocketPicker from './components/PocketPicker.vue'
  import ModelSelect from '@/components/design/ModelSelect.vue'
  import ModelParameterForm from '@/components/design/ModelParameterForm.vue'
  import { useModelOptions } from '@/composables/useModelOptions'
  import { resolveToolBySlug, submitDesignTask } from '@/api/design'
  import {
    buildDefaultValues,
    normalizeParameters,
    validateParameters,
    type ParameterValues
  } from '@/domain/tools/parameterSchema'
  import type { DesignPocketSelection, ResolvedDesignTool } from '@/types/design'
  import type { ParameterFieldOverride } from '@/components/design/ModelParameterForm.vue'
  import { MOLECULE_GENERATION_TOOL_SLUG } from '@/types/design'

  const router = useRouter()
  const route = useRoute()
  const { t } = useI18n()

  const props = withDefaults(defineProps<{ initialProjectId?: string }>(), {
    initialProjectId: ''
  })

  const defaultProjectId = computed(() => {
    if (props.initialProjectId) return props.initialProjectId
    return typeof route.query.project_id === 'string' ? route.query.project_id : ''
  })

  const resolving = ref(false)
  const submitting = ref(false)
  const resolvedTool = ref<ResolvedDesignTool | null>(null)
  const toolError = ref(false)
  const pocketSelection = ref<DesignPocketSelection | null>(null)

  // 同类分子生成模型可自由选择；默认 pocket2mol；参数 schema 随模型切换。
  const {
    options: modelOptions,
    selectedSlug,
    selectedOption,
    loading: modelLoading,
    load: loadModels
  } = useModelOptions('molecule_generation', { defaultSlug: MOLECULE_GENERATION_TOOL_SLUG })

  const form = reactive<{ params: ParameterValues }>({ params: {} })

  const hiddenParams: Record<string, ParameterFieldOverride> = {
    center_x: { hidden: true },
    center_y: { hidden: true },
    center_z: { hidden: true },
    pocket_radius: { hidden: false }
  }

  const hasCenter = computed(() => {
    const center = pocketSelection.value?.center
    return Boolean(
      center &&
        center.x !== null &&
        center.y !== null &&
        center.z !== null &&
        Number.isFinite(center.x) &&
        Number.isFinite(center.y) &&
        Number.isFinite(center.z)
    )
  })

  const canSubmit = computed(
    () =>
      Boolean(
        resolvedTool.value &&
          pocketSelection.value?.structureFileId &&
          hasCenter.value &&
          validateParameters(selectedOption.value?.parameterSchema ?? null, form.params).length === 0
      )
  )

  const centerText = computed(() => {
    const center = pocketSelection.value?.center
    if (!center || center.x === null || center.y === null || center.z === null) return '-'
    return `${center.x.toFixed(2)}, ${center.y.toFixed(2)}, ${center.z.toFixed(2)} Å`
  })

  const boxText = computed(() => {
    const box = pocketSelection.value?.boxSize
    if (!box || box.x === null || box.y === null || box.z === null) return '-'
    return `${box.x.toFixed(1)} × ${box.y.toFixed(1)} × ${box.z.toFixed(1)} Å`
  })

  function toNumber(value: unknown, fallback: number): number {
    const parsed = typeof value === 'number' ? value : Number(value)
    return Number.isFinite(parsed) ? parsed : fallback
  }

  function validate(): string | null {
    if (!pocketSelection.value?.structureFileId) {
      return t('design.molecule.pocketMissingFile')
    }
    if (!hasCenter.value) {
      return t('design.molecule.pocketMissingCenter')
    }
    const errors = validateParameters(selectedOption.value?.parameterSchema ?? null, form.params)
    if (errors.length > 0) return t('design.molecule.invalidNum')
    return null
  }

  async function loadTool(): Promise<void> {
    resolving.value = true
    toolError.value = false
    try {
      resolvedTool.value = await resolveToolBySlug(selectedSlug.value)
      if (!resolvedTool.value) {
        toolError.value = true
      }
    } catch {
      toolError.value = true
    } finally {
      resolving.value = false
    }
  }

  async function handleSubmit(): Promise<void> {
    if (!resolvedTool.value || !pocketSelection.value) {
      message.warning(t('design.molecule.selectPocketFirst'))
      return
    }
    const invalid = validate()
    if (invalid) {
      message.warning(invalid)
      return
    }

    const selection = pocketSelection.value
    const center = selection.center
    const schema = selectedOption.value?.parameterSchema ?? null
    const params = {
      ...normalizeParameters(schema, form.params),
      center_x: toNumber(center?.x, 0),
      center_y: toNumber(center?.y, 0),
      center_z: toNumber(center?.z, 0)
    }

    submitting.value = true
    try {
      const response = await submitDesignTask({
        name: t('design.molecule.taskName'),
        projectId: selection.projectId,
        toolId: resolvedTool.value.tool.id,
        toolVersionId: resolvedTool.value.version.id,
        params,
        standardInputUploads: { protein_pdb: selection.structureFileId as string }
      })
      message.success(t('design.molecule.submitted'))
      await router.push({ name: 'GenerationResults', params: { id: response.data.id } })
    } catch {
      message.error(t('design.molecule.failed'))
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

  watch(
    pocketSelection,
    selection => {
      const box = selection?.boxSize
      if (!box) return
      const dims = [box.x, box.y, box.z].filter(
        (value): value is number => typeof value === 'number' && Number.isFinite(value) && value > 0
      )
      if (dims.length > 0) {
        form.params = {
          ...form.params,
          pocket_radius: Number((Math.max(...dims) / 2).toFixed(1))
        }
      }
    },
    { deep: true }
  )

  onMounted(() => {
    void loadModels().then(() => loadTool())
  })

  watch(selectedSlug, () => {
    void loadTool()
  })
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

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

  .pocket-alert {
    margin-bottom: 24px;
  }

  .number-input {
    width: 100%;
  }

  .param-hint {
    margin: 0;
    color: @text-tertiary;
    font-size: @font-size-sm;
  }

  .design-actions {
    display: flex;
    justify-content: flex-end;
  }
</style>
