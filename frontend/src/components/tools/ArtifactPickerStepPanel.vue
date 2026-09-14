<template>
  <div class="artifact-step-panel">
    <div class="artifact-step-header">
      <div class="artifact-step-copy">
        <span class="artifact-step-kicker">{{ label }}</span>
        <strong class="artifact-step-title">{{ title }}</strong>
      </div>
      <a-tag class="artifact-step-count">{{ count }}</a-tag>
    </div>

    <div class="artifact-step-list">
      <ArtifactPickerStepOption
        v-for="option in options"
        :key="option.id"
        :title="option.title"
        :meta="option.meta"
        :right-text="option.rightText"
        :right-color="option.rightColor"
        :selected="option.selected"
        :focused="option.focused"
        @select="emit('select', option.id)"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
  import ArtifactPickerStepOption from './ArtifactPickerStepOption.vue'

  interface ArtifactPickerStepPanelOption {
    id: string
    title: string
    meta: string
    rightText?: string | number
    rightColor?: string
    selected?: boolean
    focused?: boolean
  }

  defineProps<{
    label: string
    title: string
    count: string | number
    options: ArtifactPickerStepPanelOption[]
  }>()

  const emit = defineEmits<{
    select: [id: string]
  }>()
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .artifact-step-panel {
    display: flex;
    flex-direction: column;
    gap: @spacing-sm;
    padding: @spacing-md;
    border: 1px solid #d8e1ee;
    border-radius: @border-radius-md;
    background: linear-gradient(180deg, @bg-elevated 0%, @accent-color-light 100%);
  }

  .artifact-step-header {
    display: flex;
    align-items: flex-start;
    justify-content: space-between;
    gap: @spacing-sm;
  }

  .artifact-step-copy {
    display: flex;
    flex-direction: column;
    gap: @spacing-xs;
    min-width: 0;
  }

  .artifact-step-kicker {
    color: @text-color-light-secondary;
    font-size: @font-size-xs;
  }

  .artifact-step-title {
    color: @text-color-light-primary;
    font-size: @font-size-sm;
    font-weight: @font-weight-semibold;
  }

  .artifact-step-count {
    margin-inline-end: 0;
  }

  .artifact-step-list {
    display: flex;
    flex-direction: column;
    gap: @spacing-xs;
  }
</style>
