<template>
  <!--
    后台刷新指示条：只在「已有内容、正在取新数据」时出现。

    列表页过去直接用骨架屏替换表格/卡片（`SkeletonList v-if="loading"`），
    每次自动刷新都会把整块内容卸载再挂回，视觉上就是一下一下的白闪。
    自动刷新是后台行为，用户的视线没要求它「重新出现」——用一条 2px 的
    进度条表示「在取数据」即可，内容保持原地不动。
  -->
  <div
    v-if="active"
    class="loading-bar"
    role="progressbar"
    aria-label="refreshing"
    data-testid="inline-loading-bar"
  >
    <span class="loading-bar__indicator" />
  </div>
</template>

<script setup lang="ts">
defineProps<{ active: boolean }>()
</script>

<style scoped lang="less">
@import '@/assets/styles/variables.less';

.loading-bar {
  position: relative;
  height: 2px;
  overflow: hidden;
  border-radius: 2px;
  background: @border-color-split;
}

.loading-bar__indicator {
  position: absolute;
  top: 0;
  left: 0;
  height: 100%;
  width: 40%;
  border-radius: 2px;
  background: @primary-color;
  animation: loading-bar-slide 1.1s ease-in-out infinite;
}

@keyframes loading-bar-slide {
  0% {
    transform: translateX(-100%);
  }

  100% {
    transform: translateX(250%);
  }
}

@media (prefers-reduced-motion: reduce) {
  .loading-bar__indicator {
    animation-duration: 2.4s;
  }
}
</style>
