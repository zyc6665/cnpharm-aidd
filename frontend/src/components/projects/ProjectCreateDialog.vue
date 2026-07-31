<template>
  <a-modal
    :open="open"
    :title="t('workspace.createProject')"
    :confirm-loading="submitting"
    :ok-text="t('common.create')"
    :cancel-text="t('common.cancel')"
    @ok="submit"
    @cancel="close"
  >
    <a-form layout="vertical" @submit.prevent="submit">
      <a-form-item
        :label="t('workspace.project.name')"
        :validate-status="nameError ? 'error' : undefined"
        :help="nameError"
        required
      >
        <a-input
          v-model:value="name"
          :maxlength="160"
          :placeholder="t('workspace.project.namePlaceholder')"
          @input="nameError = ''"
        />
      </a-form-item>
      <a-form-item :label="t('workspace.project.goal')">
        <a-textarea
          v-model:value="goal"
          :maxlength="20000"
          :rows="4"
          :placeholder="t('workspace.project.goalPlaceholder')"
        />
      </a-form-item>
      <a-alert v-if="submitError" type="error" show-icon :message="submitError" />
    </a-form>
  </a-modal>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { useI18n } from 'vue-i18n'
import { createProject } from '@/api/projects'
import type { ResearchProject } from '@/types/projects'

const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{
  'update:open': [value: boolean]
  created: [project: ResearchProject]
}>()

const { t } = useI18n()
const name = ref('')
const goal = ref('')
const nameError = ref('')
const submitError = ref('')
const submitting = ref(false)

watch(() => props.open, value => {
  if (value) {
    name.value = ''
    goal.value = ''
    nameError.value = ''
    submitError.value = ''
  }
})

const close = () => emit('update:open', false)

async function submit() {
  const normalizedName = name.value.trim()
  if (!normalizedName) {
    nameError.value = t('workspace.project.nameRequired')
    return
  }
  if (submitting.value) return

  submitting.value = true
  submitError.value = ''
  try {
    const response = await createProject({
      name: normalizedName,
      ...(goal.value.trim() ? { goal: goal.value.trim() } : {})
    })
    emit('created', response.data)
    close()
  } catch {
    submitError.value = t('workspace.project.createFailed')
  } finally {
    submitting.value = false
  }
}
</script>

