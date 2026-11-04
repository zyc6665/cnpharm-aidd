<template>
  <div class="structure-predict-form" data-testid="structure-predict-form">
    <a-form layout="vertical">
      <a-row :gutter="12">
        <a-col :xs="24" :sm="8">
          <a-form-item :label="t('targets.predict.model')">
            <a-input v-model:value="form.modelName" data-testid="structure-predict-model" />
          </a-form-item>
        </a-col>
        <a-col :xs="24" :sm="8">
          <a-form-item :label="t('targets.predict.numRecycles')">
            <a-input-number
              v-model:value="form.numRecycles"
              class="number-input"
              :min="1"
              :max="20"
              :precision="0"
            />
          </a-form-item>
        </a-col>
        <a-col :xs="24" :sm="8">
          <a-form-item :label="t('targets.predict.seed')">
            <a-input-number v-model:value="form.seed" class="number-input" :min="0" :precision="0" />
          </a-form-item>
        </a-col>
        <a-col :xs="24" :sm="8">
          <a-form-item :label="t('targets.predict.useMsa')" :extra="t('targets.predict.useMsaHint')">
            <a-switch v-model:checked="form.useMsa" />
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
import { computed, ref } from 'vue'
import { useI18n } from 'vue-i18n'
import { useStructurePrediction } from '@/composables/useStructurePrediction'
import { waitForTaskCompletion } from '@/composables/useTaskCompletion'

const props = defineProps<{ proteinId: string }>()
const emit = defineEmits<{
  (event: 'submitted', taskId: string): void
  (event: 'completed', taskId: string): void
  (event: 'error', message: string): void
}>()

const { t } = useI18n()
const { form, submitting, error, submit } = useStructurePrediction()
const waiting = ref(false)

const errorText = computed(() => {
  if (!error.value) return ''
  if (error.value === 'invalid-num-recycles' || error.value === 'invalid-seed') {
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
