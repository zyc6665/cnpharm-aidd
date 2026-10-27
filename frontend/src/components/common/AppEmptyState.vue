<template>
  <div class="app-empty" :class="[`app-empty--${size}`]">
    <!--
      自绘图形而不是 antd 的 `a-empty` 默认插图：后者是一张灰蓝色的纸箱位图式 SVG，
      在深色底（#09090b）上像一块发白的雾，整页看上去像「加载失败」。
      这里用与品牌标识同源的六元环线稿，单色描边走 --theme-* 变量，两套主题共用一份。
    -->
    <svg
      v-if="showGraphic"
      class="app-empty__graphic"
      viewBox="0 0 96 96"
      role="img"
      :aria-label="title || description"
    >
      <g
        fill="none"
        stroke="currentColor"
        stroke-width="1.6"
        stroke-linejoin="round"
        stroke-linecap="round"
        opacity="0.5"
      >
        <path d="M48 12 75 27.6 75 58.8 48 74.4 21 58.8 21 27.6 Z" />
        <path d="M48 27.4 62.4 35.7 62.4 54.3 48 62.6 33.6 54.3 33.6 35.7 Z" opacity="0.6" />
      </g>
      <circle cx="48" cy="46" r="4.2" fill="currentColor" opacity="0.32" />
    </svg>

    <p v-if="title" class="app-empty__title">{{ title }}</p>
    <p v-if="description" class="app-empty__description">{{ description }}</p>

    <div v-if="$slots.default" class="app-empty__actions">
      <slot />
    </div>
  </div>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    /** 一句话说明这一块是干什么的，不是「暂无数据」。 */
    title?: string
    /** 补充说明「为什么现在是空的」以及「怎么让它不空」。 */
    description?: string
    size?: 'default' | 'compact'
    showGraphic?: boolean
  }>(),
  { title: '', description: '', size: 'default', showGraphic: true }
)
</script>

<style scoped lang="less">
@import '@/assets/styles/variables.less';

.app-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: @spacing-xs;
  padding: @spacing-xl @spacing-md;
  color: @text-tertiary;
  text-align: center;
}

.app-empty--compact {
  padding: @spacing-md;

  .app-empty__graphic {
    width: 40px;
    height: 40px;
    margin-bottom: 2px;
  }

  .app-empty__title {
    font-size: @font-size-sm;
  }

  .app-empty__description {
    font-size: @font-size-xs;
  }
}

.app-empty__graphic {
  width: 64px;
  height: 64px;
  margin-bottom: @spacing-xs;
  color: @text-disabled;
}

.app-empty__title {
  margin: 0;
  color: @text-secondary;
  font-size: @font-size-md;
  font-weight: @font-weight-medium;
}

.app-empty__description {
  max-width: 46em;
  margin: 0;
  color: @text-tertiary;
  font-size: @font-size-sm;
  line-height: @line-height-base;
}

.app-empty__actions {
  display: flex;
  flex-wrap: wrap;
  gap: @spacing-sm;
  justify-content: center;
  margin-top: @spacing-sm;
}
</style>
