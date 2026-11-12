<template>
  <main class="structure-predict-page" data-testid="structure-predict-page">
    <AppBackLink
      :fallback="backLink"
      :parent-label="t('targets.predict.backToTarget')"
    />

    <AppPageHeader :title="t('targets.predict.title')" :subtitle="t('targets.predict.subtitle')" />

    <AppErrorState
      v-if="loadError"
      data-testid="structure-predict-error"
      code="ERR"
      :title="t('targets.loadFailed')"
      :description="t('targets.loadFailedHint')"
      :action-text="t('targets.predict.backToTarget')"
      :to="backLink"
    />

    <SkeletonDetail v-else-if="loading && !protein" />

    <template v-else>
      <a-alert
        v-if="sequenceMissing"
        class="predict-alert"
        type="warning"
        show-icon
        :message="t('targets.predict.sequenceMissing')"
        data-testid="predict-sequence-missing"
      />

      <a-descriptions
        class="protein-summary"
        data-testid="predict-protein-summary"
        :column="2"
        size="small"
        bordered
      >
        <a-descriptions-item :label="t('targets.detail.name')">
          {{ protein ? protein.name : '-' }}
        </a-descriptions-item>
        <a-descriptions-item :label="t('targets.detail.seqLength')">
          {{ protein?.seq_length ?? '-' }}
        </a-descriptions-item>
      </a-descriptions>

      <a-form class="predict-form" layout="vertical" data-testid="predict-form">
        <a-form-item :label="t('targets.predict.model')">
          <ModelSelect v-model="selectedSlug" :options="modelOptions" :loading="modelLoading" />
        </a-form-item>
        <ModelParameterForm
          v-if="selectedOption?.parameterSchema"
          v-model="form.params"
          :schema="selectedOption.parameterSchema"
          :overrides="hiddenParams"
          :disabled="submitting"
        />

        <p class="resource-note" data-testid="predict-resource-note">
          <a-typography-text type="secondary">
            {{ t('targets.predict.resourceManagedByPlatform') }}
          </a-typography-text>
        </p>

        <div class="predict-actions">
          <a-button
            type="primary"
            :loading="submitting"
            :disabled="sequenceMissing"
            data-testid="predict-submit"
            @click="handleSubmit"
          >
            {{ t('targets.predict.submit') }}
          </a-button>
        </div>
      </a-form>
    </template>
  </main>
</template>

<script setup lang="ts">
  import { computed, onMounted, ref, watch } from 'vue'
  import { useRoute, useRouter } from 'vue-router'
  import { message } from 'ant-design-vue'
  import { useI18n } from 'vue-i18n'
  import AppPageHeader from '@/components/common/AppPageHeader.vue'
  import AppErrorState from '@/components/common/AppErrorState.vue'
  import SkeletonDetail from '@/components/common/SkeletonDetail.vue'
  import ModelSelect from '@/components/design/ModelSelect.vue'
  import ModelParameterForm from '@/components/design/ModelParameterForm.vue'
  import { getProtein } from '@/api/targets'
  import { useStructurePrediction } from '@/composables/useStructurePrediction'
  import { useModelOptions } from '@/composables/useModelOptions'
  import { STRUCTURE_PREDICT_TOOL_SLUG } from '@/types/design'
  import type { ParameterFieldOverride } from '@/components/design/ModelParameterForm.vue'
  import type { ProteinDetail } from '@/types/targets'
  import AppBackLink from '@/components/common/AppBackLink.vue'

  const route = useRoute()
  const router = useRouter()
  const { t } = useI18n()

  const proteinId = computed(() => String(route.params.proteinId || ''))
  const protein = ref<ProteinDetail | null>(null)
  const loading = ref(false)
  const loadError = ref(false)

  const hiddenParams: Record<string, ParameterFieldOverride> = {
    sequence: { hidden: true },
    seq_length: { hidden: true }
  }

  // 与「上游接力条」共用同一套结构预测表单/提交逻辑，避免两份实现漂移。
  const { form, submitting, error, setSchema, submit } = useStructurePrediction()
  const {
    options: modelOptions,
    selectedSlug,
    selectedOption,
    loading: modelLoading,
    load: loadModels
  } = useModelOptions('structure_prediction', { defaultSlug: STRUCTURE_PREDICT_TOOL_SLUG })

  watch(
    selectedOption,
    option => {
      form.modelSlug = option?.slug ?? selectedSlug.value
      setSchema(option?.parameterSchema ?? null)
    },
    { immediate: true }
  )

  const sequenceMissing = computed(() => {
    if (!protein.value) {
      return false
    }
    return !protein.value.sequence || protein.value.sequence.trim().length === 0
  })

  const backLink = computed(() => {
    const targetId = protein.value?.target_id
    return targetId ? `/targets/${targetId}` : '/'
  })

  async function load() {
    if (!proteinId.value) {
      return
    }
    loading.value = true
    loadError.value = false
    try {
      const response = await getProtein(proteinId.value)
      protein.value = response.data
    } catch {
      loadError.value = true
      protein.value = null
    } finally {
      loading.value = false
    }
  }

  async function handleSubmit() {
    const taskId = await submit(proteinId.value, selectedOption.value?.parameterSchema ?? null)
    if (!taskId) {
      message.warning(
        error.value === 'submit-failed'
          ? t('targets.predict.failed')
          : t('targets.predict.invalidNumber')
      )
      return
    }
    message.success(t('targets.predict.submitted'))
    await router.push({ name: 'TaskDetail', params: { id: taskId } })
  }

  onMounted(() => {
    void load()
    void loadModels()
  })
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .structure-predict-page {
    max-width: @page-max-width;
    margin: 0 auto;
    padding: @spacing-xl @spacing-lg @spacing-xxl;
  }

  .back-link {
    display: inline-block;
    margin-bottom: @spacing-lg;
    color: @text-tertiary;

    &:hover {
      color: @accent-color;
    }
  }

  .predict-alert {
    margin-bottom: @spacing-md;
  }

  .protein-summary {
    margin-bottom: @spacing-lg;
  }

  .predict-form {
    padding: @spacing-lg;
    border: 1px solid @border-color;
    border-radius: @border-radius-md;
    background: @bg-surface;
  }

  .number-input {
    width: 180px;
  }

  .resource-note {
    margin: 0 0 @spacing-md;
    font-size: @font-size-sm;
  }

  .predict-actions {
    display: flex;
    justify-content: flex-end;
  }
</style>
