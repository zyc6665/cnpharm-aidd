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
        <h3 class="design-section__title">{{ t('design.section.inputs') }}</h3>
        <PocketPicker v-model="pocketSelection" />
      </section>

      <section class="design-section">
        <h3 class="design-section__title">{{ t('design.section.parameters') }}</h3>
        <a-form layout="vertical" data-testid="peptide-form">
          <a-row :gutter="16">
            <a-col :xs="24" :sm="12" :lg="8">
              <a-form-item :label="t('design.peptide.numPeptides')">
                <a-input-number
                  v-model:value="form.numPeptides"
                  class="number-input"
                  :min="1"
                  :max="500"
                  :precision="0"
                  data-testid="peptide-num"
                />
              </a-form-item>
            </a-col>
            <a-col :xs="24" :sm="12" :lg="8">
              <a-form-item :label="t('design.peptide.seed')">
                <a-input-number
                  v-model:value="form.seed"
                  class="number-input"
                  :min="0"
                  :precision="0"
                  data-testid="peptide-seed"
                />
              </a-form-item>
            </a-col>
          </a-row>

          <a-row :gutter="16">
            <a-col :xs="24" :sm="12" :lg="8">
              <a-form-item :label="t('design.peptide.lengthMin')">
                <a-input-number
                  v-model:value="form.lengthMin"
                  class="number-input"
                  :min="1"
                  :precision="0"
                  data-testid="peptide-length-min"
                />
              </a-form-item>
            </a-col>
            <a-col :xs="24" :sm="12" :lg="8">
              <a-form-item :label="t('design.peptide.lengthMax')">
                <a-input-number
                  v-model:value="form.lengthMax"
                  class="number-input"
                  :min="1"
                  :precision="0"
                  data-testid="peptide-length-max"
                />
              </a-form-item>
            </a-col>
          </a-row>
        </a-form>
      </section>

      <div class="design-actions">
        <a-button
          type="primary"
          :loading="submitting"
          :disabled="!pocketSelection || !resolvedTool"
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
  import { onMounted, reactive, ref } from 'vue'
  import { useRouter } from 'vue-router'
  import { message } from 'ant-design-vue'
  import { useI18n } from 'vue-i18n'
  import AppPageHeader from '@/components/common/AppPageHeader.vue'
  import PocketPicker from './components/PocketPicker.vue'
  import {
    resolvePocketInputBinding,
    resolveToolBySlug,
    submitDesignTask,
  } from '@/api/design'
  import type { DesignPocketSelection, ResolvedDesignTool } from '@/types/design'
  import { PEPTIDE_DESIGN_TOOL_SLUG } from '@/types/design'

  const router = useRouter()
  const { t } = useI18n()

  const resolving = ref(false)
  const submitting = ref(false)
  const resolvedTool = ref<ResolvedDesignTool | null>(null)
  const toolError = ref(false)
  const pocketSelection = ref<DesignPocketSelection | null>(null)

  const form = reactive({
    numPeptides: 50,
    lengthMin: 8,
    lengthMax: 15,
    seed: 42,
  })

  function toNumber(value: unknown, fallback: number): number {
    const parsed = typeof value === 'number' ? value : Number(value)
    return Number.isFinite(parsed) ? parsed : fallback
  }

  function validate(): string | null {
    const numPeptides = toNumber(form.numPeptides, 50)
    const lengthMin = toNumber(form.lengthMin, 8)
    const lengthMax = toNumber(form.lengthMax, 15)
    const seed = toNumber(form.seed, 42)

    if (numPeptides < 1 || numPeptides > 500) {
      return t('design.peptide.invalidNum')
    }
    if (lengthMin < 1 || lengthMax <= lengthMin) {
      return t('design.peptide.invalidLength')
    }
    if (seed < 0) {
      return t('design.peptide.invalidSeed')
    }
    return null
  }

  async function loadTool(): Promise<void> {
    resolving.value = true
    toolError.value = false
    try {
      resolvedTool.value = await resolveToolBySlug(PEPTIDE_DESIGN_TOOL_SLUG)
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
      message.warning(t('design.peptide.selectPocketFirst'))
      return
    }
    const invalid = validate()
    if (invalid) {
      message.warning(invalid)
      return
    }

    const params = {
      num_peptides: toNumber(form.numPeptides, 50),
      length_min: toNumber(form.lengthMin, 8),
      length_max: toNumber(form.lengthMax, 15),
      seed: toNumber(form.seed, 42),
    }

    submitting.value = true
    try {
      const inputBindings = await resolvePocketInputBinding(
        pocketSelection.value.projectId,
        pocketSelection.value.pocketId
      )
      const response = await submitDesignTask({
        name: t('design.peptide.taskName'),
        projectId: pocketSelection.value.projectId,
        toolId: resolvedTool.value.tool.id,
        toolVersionId: resolvedTool.value.version.id,
        params,
        inputBindings,
      })
      message.success(t('design.peptide.submitted'))
      await router.push({ name: 'GenerationResults', params: { id: response.data.id } })
    } catch {
      message.error(t('design.peptide.failed'))
    } finally {
      submitting.value = false
    }
  }

  onMounted(() => {
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

  .number-input {
    width: 100%;
  }

  .design-actions {
    display: flex;
    justify-content: flex-end;
  }
</style>
