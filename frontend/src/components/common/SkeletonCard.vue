<template>
  <div class="sk-card">
    <div class="sk-line sk-line-short"></div>
    <div class="sk-line sk-line-long"></div>
    <div class="sk-line sk-line-medium"></div>
    <div class="sk-line sk-line-long mt-md"></div>
  </div>
</template>

<style scoped lang="less">
@import '@/assets/styles/variables.less';

.sk-card {
  .card();
  padding: @spacing-lg;
}

.sk-line {
  height: 12px;
  border-radius: 3px;
  background: @bg-hover;
  margin-bottom: @spacing-sm;
  animation: skeletonPulse 2s ease-in-out infinite;

  &-short { width: 40%; }
  &-medium { width: 65%; }
  &-long { width: 90%; }

  &.mt-md { margin-top: @spacing-md; }
}
</style>
