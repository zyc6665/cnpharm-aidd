<template>
  <div class="node-input-binding" data-testid="node-input-binding">
    <div class="binding-header">
      <span class="section-title">{{ t('workflow.inspector.inputBindingTitle') }}</span>
    </div>

    <a-alert
      v-if="!requirement"
      type="info"
      show-icon
      :message="t('workflow.inspector.inputBindingUnresolved')"
    />

    <template v-else>
      <div class="binding-field">
        <span class="binding-label">{{ requirement.label }}</span>
        <a-select
          :value="selections[requirement.key]"
          :options="options"
          :loading="loading"
          :placeholder="t('workflow.inspector.inputBindingPlaceholder')"
          allow-clear
          show-search
          option-filter-prop="label"
          data-testid="node-input-binding-select"
          @change="selectInput"
        />
        <a-upload
          :show-upload-list="false"
          :before-upload="beforeUpload"
        >
          <a-button
            size="small"
            :disabled="!canUpload"
            :loading="uploadingKey === requirement.key"
            data-testid="node-input-binding-upload"
          >
            {{
              t(
                uploadingKey === requirement.key
                  ? 'workflow.inspector.inputBindingUploading'
                  : 'workflow.inspector.inputBindingUpload'
              )
            }}
          </a-button>
        </a-upload>
      </div>

      <p v-if="!options.length" class="binding-hint binding-hint--empty" data-testid="node-input-binding-empty">
        {{ t('workflow.inspector.inputBindingNoArtifact') }}
      </p>
      <p class="binding-hint">{{ t('workflow.inspector.inputBindingHint') }}</p>
    </template>
  </div>
</template>

<script setup lang="ts">
  import { computed } from 'vue'
  import { useI18n } from 'vue-i18n'
  import type { WorkflowInputRequirement } from '@/workflow/workflow-definitions'
  import type { WorkflowCanvasNode, WorkflowCanvasPreset } from '@/workflow/canvas-types'

  const props = defineProps<{
    node: WorkflowCanvasNode
    template?: WorkflowCanvasPreset | null
    requirements: WorkflowInputRequirement[]
    selections: Record<string, string | undefined>
    optionsBySemanticType: Record<string, Array<{ value: string; label: string }>>
    loading?: boolean
    canUpload?: boolean
    uploadingKey?: string | null
  }>()

  const emit = defineEmits<{
    select: [requirementKey: string, artifactId: string | undefined]
    upload: [requirementKey: string, file: File]
  }>()

  const { t } = useI18n()

  /**
   * 输入节点的需求键：优先取节点自己声明的 `requiredInputTypes`，
   * 否则回退到该节点输出边上的 artifactType（预置流程里两者是同一个键，
   * 例如 `input-protein -> tool-protein-preparation` 的边标着 `protein_pdb`）。
   */
  const requirementKey = computed<string | null>(() => {
    const declared = props.node.requiredInputTypes?.[0]
    if (declared) {
      return String(declared)
    }

    const edge = (props.template?.edges ?? []).find(candidate => candidate.source === props.node.id)
    return edge?.artifactType ? String(edge.artifactType) : null
  })

  const requirement = computed<WorkflowInputRequirement | null>(() => {
    const key = requirementKey.value
    if (!key) {
      return null
    }
    return (
      props.requirements.find(
        candidate => candidate.key === key || candidate.semanticType === key
      ) ?? { key, semanticType: key, label: key }
    )
  })

  const options = computed(() => {
    const target = requirement.value
    if (!target) {
      return []
    }
    return props.optionsBySemanticType[target.semanticType] ?? props.optionsBySemanticType[target.key] ?? []
  })

  function selectInput(value: unknown) {
    const target = requirement.value
    if (!target) {
      return
    }
    emit('select', target.key, typeof value === 'string' ? value : undefined)
  }

  function beforeUpload(file: File) {
    const target = requirement.value
    if (target) {
      emit('upload', target.key, file)
    }
    return false
  }
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .node-input-binding {
    display: flex;
    flex-direction: column;
    gap: @spacing-sm;
  }

  .section-title {
    font-size: 12px;
    color: @text-color-secondary;
  }

  .binding-field {
    display: flex;
    flex-direction: column;
    gap: @spacing-sm;
  }

  .binding-label {
    font-size: 13px;
  }

  .binding-hint {
    margin: 0;
    font-size: 12px;
    color: @text-color-secondary;
  }

  .binding-hint--empty {
    color: @warning-color;
  }
</style>
