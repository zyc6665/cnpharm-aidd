<template>
  <div class="sk-list">
    <div v-for="i in count" :key="i" class="sk-list-item">
      <span class="sk-dot"></span>
      <div class="sk-lines">
        <div class="sk-line" :style="{ width: widths[(i - 1) % widths.length] }"></div>
        <div class="sk-line sk-line-sm"></div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
withDefaults(defineProps<{ count?: number }>(), { count: 5 })
const widths = ['55%', '72%', '48%', '68%', '60%']
</script>

<style scoped lang="less">
@import '@/assets/styles/variables.less';

.sk-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.sk-list-item {
  display: flex;
  align-items: center;
  gap: @spacing-sm;
  padding: @spacing-sm @spacing-md;
  border-radius: @border-radius-md;
}

.sk-dot {
  width: 8px;
  height: 8px;
  border-radius: @border-radius-round;
  background: @bg-hover;
  flex-shrink: 0;
  animation: skeletonPulse 2s ease-in-out infinite;
}

.sk-lines {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.sk-line {
  height: 10px;
  border-radius: 3px;
  background: @bg-hover;
  animation: skeletonPulse 2s ease-in-out infinite;
}

.sk-line-sm {
  width: 40%;
  height: 8px;
}
</style>
