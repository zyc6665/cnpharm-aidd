<template>
  <div class="structure-predict-form" data-testid="structure-predict-form">
    <a-form layout="vertical">
      <a-row :gutter="12">
        <a-col :xs="24" :sm="8">
          <a-form-item :label="t('targets.predict.model')">
            <ModelSelect v-model="selectedSlug" :options="modelOptions" :loading="modelLoading" />
          </a-form-item>
        </a-col>
        <a-col :xs="12" :sm="4">
          <a-form-item :label="t('targets.predict.samplingSteps')">
            <a-input-number
              v-model:value="form.samplingSteps"
              class="number-input"
              :min="10"
              :max="1000"
              :step="10"
              :precision="0"
            />
          </a-form-item>
        </a-col>
        <a-col :xs="12" :sm="4">
          <a-form-item :label="t('targets.predict.recyclingSteps')">
            <a-input-number
              v-model:value="form.recyclingSteps"
              class="number-input"
              :min="1"
              :max="10"
              :precision="0"
            />
          </a-form-item>
        </a-col>
        <a-col :xs="12" :sm="4">
          <a-form-item :label="t('targets.predict.diffusionSamples')">
            <a-input-number
              v-model:value="form.diffusionSamples"
              class="number-input"
              :min="1"
              :max="10"
              :precision="0"
            />
          </a-form-item>
        </a-col>
        <a-col :xs="12" :sm="4">
          <a-form-item :label="t('targets.predict.seed')">
            <a-input-number v-model:value="form.seed" class="number-input" :min="0" :precision="0" />
          </a-form-item>
        </a-col>
      </a-row>

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
import { STRUCTURE_PREDICT_TOOL_SLUG } from '@/types/design'

const props = defineProps<{ proteinId: string }>()
const emit = defineEmits<{
  (event: 'submitted', taskId: string): void
  (event: 'completed', taskId: string): void
  (event: 'error', message: string): void
}>()

const { t } = useI18n()
const { form, submitting, error, submit } = useStructurePrediction()
const waiting = ref(false)

// 结构预测模型：同类可自由选择，默认 boltz2；把所选写成 model_ref.name(slug)。
const {
  options: modelOptions,
  selectedSlug,
  loading: modelLoading,
  load: loadModels
} = useModelOptions('structure_prediction', { defaultSlug: STRUCTURE_PREDICT_TOOL_SLUG })

watch(
  selectedSlug,
  slug => {
    form.modelSlug = slug
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
  const taskId = await submit(props.proteinId)
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
