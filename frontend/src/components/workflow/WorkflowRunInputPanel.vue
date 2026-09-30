<template>
  <div class="workflow-run-input-panel">
    <div class="run-input-header">
      <span>{{ t('workflow.canvasPresets.requiredInputs') }}</span>
      <a-button
        v-if="displayRequirements.length > 0"
        size="small"
        :disabled="autoFillDisabled"
        @click="emit('auto-fill')"
      >
        {{ t('workflow.canvasPresets.autoFillInputs') }}
      </a-button>
    </div>
    <a-empty
      v-if="displayRequirements.length === 0"
      class="run-input-empty"
      :description="t('workflow.canvasPresets.emptyRunInputs')"
    />
    <div v-else class="run-input-grid">
      <div
        v-for="requirement in displayRequirements"
        :key="requirement.key"
        class="run-input-field"
      >
        <span>{{ requirement.label }}</span>
        <a-select
          :value="selections[requirement.key]"
          :options="resolveOptions(requirement.semanticType)"
          :placeholder="t('workflow.canvasPresets.selectInputArtifact')"
          :loading="loading"
          allow-clear
          show-search
          option-filter-prop="label"
          @change="emit('select', requirement.key, $event)"
        />
        <a-upload
          :show-upload-list="false"
          :before-upload="(file: File) => beforeUpload(requirement.key, file)"
        >
          <a-button
            size="small"
            :disabled="!canUpload"
            :loading="uploadingKey === requirement.key"
          >
            {{
              t(
                uploadingKey === requirement.key
                  ? 'workflow.canvasPresets.uploadingInput'
                  : 'workflow.canvasPresets.uploadInput'
              )
            }}
          </a-button>
        </a-upload>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
  import { computed } from 'vue'
  import { useI18n } from 'vue-i18n'
  import type { WorkflowInputRequirement } from '@/workflow/workflow-definitions'

  const props = defineProps<{
    requirements: string[]
    artifactRequirements?: WorkflowInputRequirement[]
    selections: Record<string, string | undefined>
    optionsBySemanticType: Record<string, Array<{ value: string; label: string }>>
    loading?: boolean
    autoFillDisabled?: boolean
    canUpload?: boolean
    uploadingKey?: string | null
  }>()

  const emit = defineEmits<{
    'auto-fill': []
    select: [semanticType: string, artifactId: string | undefined]
    upload: [semanticType: string, file: File]
  }>()

  const { t } = useI18n()

  const displayRequirements = computed<WorkflowInputRequirement[]>(() => {
    if (props.artifactRequirements?.length) {
      return [...props.artifactRequirements]
    }

    return props.requirements.map(semanticType => ({
      key: semanticType,
      semanticType,
      label: semanticType
    }))
  })

  function resolveOptions(semanticType: string) {
    return props.optionsBySemanticType[semanticType] ?? []
  }

  function beforeUpload(semanticType: string, file: File) {
    emit('upload', semanticType, file)
    return false
  }
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .workflow-run-input-panel {
    padding: @spacing-md;
    margin-bottom: @spacing-md;
    border: 1px solid @border-color-hover;
    border-radius: @border-radius-md;
    background: @bg-surface;
    box-shadow: @shadow-sm;
  }

  .run-input-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: @spacing-sm;
    margin-bottom: @spacing-sm;
  }

  .run-input-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    gap: @spacing-sm;
  }

  .run-input-empty {
    padding: @spacing-lg @spacing-sm;
  }

  .run-input-field {
    display: grid;
    gap: @spacing-xs;
    align-content: start;

    span {
      color: @text-color-light-secondary;
      font-size: @font-size-sm;
      font-weight: 600;
    }
  }
</style>
