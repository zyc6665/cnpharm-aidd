<template>
  <button
    type="button"
    class="artifact-step-option"
    :class="{
      'is-selected': selected,
      'is-focused': focused,
    }"
    @click="emit('select')"
  >
    <span class="artifact-step-option-copy">
      <strong class="artifact-step-option-title">{{ title }}</strong>
      <span class="artifact-step-option-meta">{{ meta }}</span>
    </span>
    <a-tag
      v-if="hasRightText"
      :color="rightColor"
      class="artifact-step-option-count"
    >
      {{ rightText }}
    </a-tag>
  </button>
</template>

<script setup lang="ts">
  import { computed } from 'vue'

  const props = withDefaults(
    defineProps<{
      title: string
      meta: string
      rightText?: string | number
      rightColor?: string
      selected?: boolean
      focused?: boolean
    }>(),
    {
      rightText: undefined,
      rightColor: undefined,
      selected: false,
      focused: false,
    }
  )

  const emit = defineEmits<{
    select: []
  }>()

  const hasRightText = computed(() => props.rightText !== undefined && props.rightText !== '')
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .artifact-step-option {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    gap: @spacing-sm;
    align-items: center;
    padding: @spacing-sm @spacing-md;
    border: 1px solid #e8edf5;
    border-radius: @border-radius-md;
    background: @bg-elevated;
    text-align: left;
    transition: border-color 0.2s ease, background 0.2s ease, box-shadow 0.2s ease;
    cursor: pointer;

    &:hover {
      border-color: rgba(59, 130, 246, 0.35);
      background: @accent-color-light;
    }

    &.is-selected {
      border-color: rgba(59, 130, 246, 0.45);
      box-shadow: 0 0 0 3px rgb(24 144 255 / 10%);
    }

    &.is-focused {
      border-color: rgba(250, 173, 20, 0.55);
      background: rgba(250, 173, 20, 0.12);
    }

    @media (max-width: @screen-md) {
      grid-template-columns: minmax(0, 1fr);
    }
  }

  .artifact-step-option-copy {
    display: flex;
    flex-direction: column;
    gap: @spacing-xs;
    min-width: 0;
  }

  .artifact-step-option-title {
    overflow: hidden;
    color: @text-color-light-primary;
    font-size: @font-size-sm;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .artifact-step-option-meta {
    overflow: hidden;
    color: @text-color-light-secondary;
    font-size: @font-size-xs;
    text-overflow: ellipsis;
    white-space: nowrap;
  }

  .artifact-step-option-count {
    margin-inline-end: 0;
    white-space: nowrap;
  }
</style>
