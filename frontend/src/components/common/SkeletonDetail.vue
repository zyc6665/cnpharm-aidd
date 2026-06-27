<template>
  <div class="sk-detail">
    <div class="sk-header">
      <div class="sk-line sk-line-lg"></div>
      <div class="sk-line sk-line-sm"></div>
    </div>
    <div class="sk-body">
      <div class="sk-block">
        <div class="sk-line sk-line-md"></div>
        <div class="sk-line sk-line-lg"></div>
        <div class="sk-line sk-line-lg"></div>
      </div>
      <div class="sk-block">
        <div class="sk-line sk-line-md"></div>
        <div class="sk-line sk-line-lg"></div>
      </div>
    </div>
    <div class="sk-sidebar">
      <div class="sk-line sk-line-md"></div>
      <div class="sk-line sk-line-lg"></div>
      <div class="sk-line sk-line-sm"></div>
    </div>
  </div>
</template>

<style scoped lang="less">
@import '@/assets/styles/variables.less';

.sk-detail {
  display: grid;
  grid-template-columns: 1fr 280px;
  grid-template-rows: auto 1fr;
  gap: @spacing-lg;
  padding: @spacing-xl;
  max-width: @container-xxl;
  margin: 0 auto;
}

.sk-header {
  grid-column: 1 / -1;
}

.sk-body {
  display: flex;
  flex-direction: column;
  gap: @spacing-lg;
}

.sk-block {
  .card();
  padding: @spacing-lg;
  display: flex;
  flex-direction: column;
  gap: @spacing-sm;
}

.sk-sidebar {
  .card();
  padding: @spacing-lg;
  display: flex;
  flex-direction: column;
  gap: @spacing-sm;
}

.sk-line {
  height: 14px;
  border-radius: 4px;
  background: @bg-hover;
  animation: skeletonPulse 2s ease-in-out infinite;
}

.sk-line-sm { width: 35%; height: 11px; }
.sk-line-md { width: 55%; }
.sk-line-lg { width: 85%; }

@media (max-width: @screen-md) {
  .sk-detail {
    grid-template-columns: 1fr;
  }
  .sk-sidebar {
    display: none;
  }
}
</style>
