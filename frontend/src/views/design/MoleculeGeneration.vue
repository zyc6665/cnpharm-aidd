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
        <h3 class="design-section__title">{{ t('design.section.inputs') }}</h3>
        <PocketPicker v-model="pocketSelection" />
      </section>

      <section class="design-section">
        <h3 class="design-section__title">{{ t('design.section.parameters') }}</h3>
        <a-form layout="vertical" data-testid="molecule-form">
          <a-row :gutter="16">
            <a-col :xs="24" :sm="12" :lg="8">
              <a-form-item :label="t('design.molecule.numMolecules')">
                <a-input-number
                  v-model:value="form.numMolecules"
                  class="number-input"
                  :min="1"
                  :max="1000"
                  :precision="0"
                  data-testid="molecule-num"
                />
              </a-form-item>
            </a-col>
            <a-col :xs="24" :sm="12" :lg="8">
              <a-form-item :label="t('design.molecule.seed')">
                <a-input-number
                  v-model:value="form.seed"
                  class="number-input"
                  :min="0"
                  :precision="0"
                  data-testid="molecule-seed"
                />
              </a-form-item>
            </a-col>
          </a-row>

          <a-row :gutter="16">
            <a-col :xs="24" :sm="12" :lg="8">
              <a-form-item :label="t('design.molecule.mwMin')">
                <a-input-number v-model:value="form.mwMin" class="number-input" :min="1" data-testid="molecule-mw-min" />
              </a-form-item>
            </a-col>
            <a-col :xs="24" :sm="12" :lg="8">
              <a-form-item :label="t('design.molecule.mwMax')">
                <a-input-number v-model:value="form.mwMax" class="number-input" :min="1" data-testid="molecule-mw-max" />
              </a-form-item>
            </a-col>
          </a-row>

          <a-row :gutter="16">
            <a-col :xs="24" :sm="12" :lg="8">
              <a-form-item :label="t('design.molecule.logpMin')">
                <a-input-number v-model:value="form.logpMin" class="number-input" data-testid="molecule-logp-min" />
              </a-form-item>
            </a-col>
            <a-col :xs="24" :sm="12" :lg="8">
              <a-form-item :label="t('design.molecule.logpMax')">
                <a-input-number v-model:value="form.logpMax" class="number-input" data-testid="molecule-logp-max" />
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
  import { MOLECULE_GENERATION_TOOL_SLUG } from '@/types/design'

  const router = useRouter()
  const { t } = useI18n()

  const resolving = ref(false)
  const submitting = ref(false)
  const resolvedTool = ref<ResolvedDesignTool | null>(null)
  const toolError = ref(false)
  const pocketSelection = ref<DesignPocketSelection | null>(null)

  const form = reactive({
    numMolecules: 100,
    mwMin: 200,
    mwMax: 600,
    logpMin: -1,
    logpMax: 5,
    seed: 42,
  })

  function toNumber(value: unknown, fallback: number): number {
    const parsed = typeof value === 'number' ? value : Number(value)
    return Number.isFinite(parsed) ? parsed : fallback
  }

  function validate(): string | null {
    const numMolecules = toNumber(form.numMolecules, 100)
    const mwMin = toNumber(form.mwMin, 200)
    const mwMax = toNumber(form.mwMax, 600)
    const logpMin = toNumber(form.logpMin, -1)
    const logpMax = toNumber(form.logpMax, 5)
    const seed = toNumber(form.seed, 42)

    if (numMolecules < 1 || numMolecules > 1000) {
      return t('design.molecule.invalidNum')
    }
    if (mwMin <= 0 || mwMax <= mwMin) {
      return t('design.molecule.invalidMw')
    }
    if (logpMax <= logpMin) {
      return t('design.molecule.invalidLogp')
    }
    if (seed < 0) {
      return t('design.molecule.invalidSeed')
    }
    return null
  }

  async function loadTool(): Promise<void> {
    resolving.value = true
    toolError.value = false
    try {
      resolvedTool.value = await resolveToolBySlug(MOLECULE_GENERATION_TOOL_SLUG)
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

    const params = {
      num_molecules: toNumber(form.numMolecules, 100),
      mw_min: toNumber(form.mwMin, 200),
      mw_max: toNumber(form.mwMax, 600),
      logp_min: toNumber(form.logpMin, -1),
      logp_max: toNumber(form.logpMax, 5),
      seed: toNumber(form.seed, 42),
    }

    submitting.value = true
    try {
      const inputBindings = await resolvePocketInputBinding(
        pocketSelection.value.projectId,
        pocketSelection.value.pocketId
      )
      const response = await submitDesignTask({
        name: t('design.molecule.taskName'),
        projectId: pocketSelection.value.projectId,
        toolId: resolvedTool.value.tool.id,
        toolVersionId: resolvedTool.value.version.id,
        params,
        inputBindings,
      })
      message.success(t('design.molecule.submitted'))
      await router.push({ name: 'GenerationResults', params: { id: response.data.id } })
    } catch {
      message.error(t('design.molecule.failed'))
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
