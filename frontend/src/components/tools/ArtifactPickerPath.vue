<template>
  <div class="artifact-path">
    <button
      v-for="segment in segments"
      :key="segment.step"
      type="button"
      class="artifact-path-segment"
      :class="{
        'is-active': activeStep === segment.step,
        'is-complete': segment.complete,
      }"
      :disabled="!segment.clickable"
      @click="emit('select', segment.step)"
    >
      <span class="artifact-path-kicker">{{ segment.label }}</span>
      <strong class="artifact-path-value">{{ segment.value }}</strong>
    </button>
  </div>
</template>

<script setup lang="ts">
  import type { ArtifactPickerPathSegment, ArtifactPickerStep } from '@/domain/tools'

  defineProps<{
    segments: ArtifactPickerPathSegment[]
    activeStep: ArtifactPickerStep
  }>()

  const emit = defineEmits<{
    select: [step: ArtifactPickerStep]
  }>()
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .artifact-path {
    display: grid;
    grid-template-columns: repeat(4, minmax(0, 1fr));
    gap: @spacing-sm;

    @media (max-width: @screen-md) {
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }
  }

  .artifact-path-segment {
    display: flex;
    flex-direction: column;
    gap: @spacing-xs;
    padding: @spacing-sm @spacing-md;
    border: 1px solid #d8e1ee;
    border-radius: @border-radius-md;
    background: @bg-elevated;
    text-align: left;
    transition: border-color 0.2s ease, box-shadow 0.2s ease, transform 0.2s ease;
    cursor: pointer;
  }

  .artifact-path-segment:disabled {
    cursor: not-allowed;
    opacity: 0.72;
  }

  .artifact-path-segment:not(:disabled):hover {
    border-color: rgba(59, 130, 246, 0.35);
    box-shadow: 0 8px 18px rgb(24 144 255 / 8%);
    transform: translateY(-1px);
  }

  .artifact-path-segment.is-active {
    border-color: rgba(59, 130, 246, 0.45);
    box-shadow: 0 0 0 3px rgb(24 144 255 / 10%);
  }

  .artifact-path-segment.is-complete .artifact-path-value {
    color: @text-color-light-primary;
  }

  .artifact-path-kicker {
    color: @text-color-light-secondary;
    font-size: @font-size-xs;
  }

  .artifact-path-value {
    overflow: hidden;
    color: @text-color-light-secondary;
    font-size: @font-size-sm;
    font-weight: @font-weight-medium;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
</style>
