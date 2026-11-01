<template>
  <div class="app-inline-error" role="alert">
    <span class="app-inline-error__icon" aria-hidden="true">
      <svg viewBox="0 0 24 24" focusable="false">
        <path
          d="M12 3.2 1.8 20.8h20.4L12 3.2Zm0 5.1c.6 0 1 .5 1 1.1v4.4a1 1 0 0 1-2 0V9.4c0-.6.4-1.1 1-1.1Zm0 8.6a1.2 1.2 0 1 1 0 2.4 1.2 1.2 0 0 1 0-2.4Z"
          fill="currentColor"
        />
      </svg>
    </span>
    <div class="app-inline-error__body">
      <p v-if="title" class="app-inline-error__title">{{ title }}</p>
      <p v-if="description" class="app-inline-error__description">{{ description }}</p>
      <p v-if="detail" class="app-inline-error__detail">{{ detail }}</p>
      <div v-if="$slots.default" class="app-inline-error__actions">
        <slot />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    /** 发生了什么，例如「结果列表加载失败」。 */
    title?: string
    /** 可能的原因，例如「网络不稳定或服务暂时不可用」。 */
    description?: string
    /** 原始错误信息等可展开的补充细节。 */
    detail?: string
  }>(),
  { title: '', description: '', detail: '' }
)
</script>

<style scoped lang="less">
@import '@/assets/styles/variables.less';

.app-inline-error {
  display: flex;
  align-items: flex-start;
  gap: @spacing-sm;
  padding: @spacing-md @spacing-lg;
  border: 1px solid @border-color;
  border-left: 3px solid @error-color;
  border-radius: @border-radius-md;
  background: @error-bg;
  color: @text-primary;
}

.app-inline-error__icon {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: @spacing-lg;
  height: @spacing-lg;
  margin-top: 1px;
  color: @error-color;

  svg {
    width: 100%;
    height: 100%;
  }
}

.app-inline-error__body {
  display: flex;
  flex-direction: column;
  gap: @spacing-xs;
  min-width: 0;
}

.app-inline-error__title {
  margin: 0;
  color: @text-primary;
  font-size: @font-size-sm;
  font-weight: @font-weight-medium;
}

.app-inline-error__description {
  margin: 0;
  color: @text-secondary;
  font-size: @font-size-sm;
  line-height: @line-height-base;
}

.app-inline-error__detail {
  margin: 0;
  color: @text-tertiary;
  font-size: @font-size-xs;
  line-height: @line-height-base;
  word-break: break-word;
}

.app-inline-error__actions {
  display: flex;
  flex-wrap: wrap;
  gap: @spacing-sm;
  margin-top: @spacing-xs;
}
</style>
