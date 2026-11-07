<template>
  <div class="structure-predict-form" data-testid="structure-predict-form">
    <a-form layout="vertical">
      <a-form-item :label="t('targets.predict.model')">
        <ModelSelect v-model="selectedSlug" :options="modelOptions" :loading="modelLoading" />
      </a-form-item>
      <ModelParameterForm
        v-if="selectedOption?.parameterSchema"
        v-model="form.params"
        :schema="selectedOption.parameterSchema"
        :overrides="hiddenParams"
        :disabled="submitting || waiting"
      />

      <a-alert v-if="errorText" type="error" show-icon :message="errorText" class="form-error" />

      <div class="form-actions">
        <span v-if="waiting" class="waiting-text">{{ t('targets.predict.waiting') }}</span>
        <a-button
          type="primary"
          :loading="submitting || waiting"
          data-testid="structure-predict-submit"
          @click="handleSubmit"
        >
          {{ t('targets.predict.submit') }}
        </a-button>
      </div>
    </a-form>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { useStructurePrediction } from '@/composables/useStructurePrediction'
import { waitForTaskCompletion } from '@/composables/useTaskCompletion'
import { useModelOptions } from '@/composables/useModelOptions'
import ModelSelect from '@/components/design/ModelSelect.vue'
import ModelParameterForm from '@/components/design/ModelParameterForm.vue'
import { STRUCTURE_PREDICT_TOOL_SLUG } from '@/types/design'
import type { ParameterFieldOverride } from '@/components/design/ModelParameterForm.vue'

const props = defineProps<{ proteinId: string }>()
const emit = defineEmits<{
  (event: 'submitted', taskId: string): void
  (event: 'completed', taskId: string): void
  (event: 'error', message: string): void
}>()

const { t } = useI18n()
const { form, submitting, error, setSchema, submit } = useStructurePrediction()
const waiting = ref(false)

const hiddenParams: Record<string, ParameterFieldOverride> = {
  sequence: { hidden: true },
  seq_length: { hidden: true }
}

// 结构预测模型：同类可自由选择，默认 boltz2；参数 schema 随模型切换。
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

onMounted(() => {
  void loadModels()
})

const errorText = computed(() => {
  if (!error.value) return ''
  if (error.value.startsWith('invalid-')) {
    return t('targets.predict.invalidNumber')
  }
  return t('targets.predict.failed')
})

async function handleSubmit(): Promise<void> {
  if (!props.proteinId) return
  const taskId = await submit(props.proteinId, selectedOption.value?.parameterSchema ?? null)
  if (!taskId) {
    emit('error', error.value || 'submit-failed')
    return
  }
  emit('submitted', taskId)
  waiting.value = true
  try {
    const result = await waitForTaskCompletion(taskId)
    if (result.ok) {
      emit('completed', taskId)
    } else {
      emit(
        'error',
        result.status === 'timeout' ? t('targets.predict.timeout') : t('targets.predict.failed')
      )
    }
  } finally {
    waiting.value = false
  }
}
</script>

<style scoped lang="less">
@import '@/assets/styles/variables.less';

.structure-predict-form {
  .number-input {
    width: 100%;
  }

  .form-error {
    margin-bottom: @spacing-md;
  }

  .form-actions {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: @spacing-md;
  }

  .waiting-text {
    color: @text-tertiary;
    font-size: @font-size-sm;
  }
}
</style>
