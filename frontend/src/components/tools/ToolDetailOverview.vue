<template>
  <div class="tool-info tool-overview card">
    <div class="tool-header">
      <div class="tool-icon">
        <span v-if="tool.icon">{{ tool.icon }}</span>
        <ToolOutlined v-else />
      </div>
      <div class="tool-meta">
        <h2 class="overview-title">{{ t('tools.toolInfo') }}</h2>
        <div class="tool-tags">
          <a-tag v-if="tool.category" color="gold">{{ tool.category }}</a-tag>
          <a-tag v-for="tag in tool.tags" :key="tag.id" :color="tag.color">
            {{ tag.name }}
          </a-tag>
        </div>
      </div>
    </div>

    <p class="tool-description">{{ tool.description }}</p>

    <div class="tool-stats">
      <span class="stat-item">
        <PlayCircleOutlined />
        {{ t('tools.usageCount') }}: {{ formatNumber(tool.statistics?.usage_count) }}
      </span>
      <span class="stat-item">
        <EyeOutlined />
        {{ t('tools.viewCount') }}: {{ formatNumber(tool.statistics?.view_count) }}
      </span>
      <span class="stat-item">
        <HeartOutlined />
        {{ t('tools.favoriteCount') }}: {{ formatNumber(tool.statistics?.favorite_count) }}
      </span>
      <span v-if="tool.current_version" class="stat-item">
        <TagOutlined />
        {{ t('tools.version') }}: v{{ tool.current_version.version }}
      </span>
    </div>

    <div v-if="tool.current_version?.changelog" class="tool-changelog">
      <h3>{{ t('tools.changelog') }}</h3>
      <p>{{ tool.current_version.changelog }}</p>
    </div>
  </div>
</template>

<script setup lang="ts">
  import { useI18n } from 'vue-i18n'
  import {
    EyeOutlined,
    HeartOutlined,
    PlayCircleOutlined,
    TagOutlined,
    ToolOutlined,
  } from '@ant-design/icons-vue'
  import type { Tool } from '@/types/models'
  import { formatToolMetricCount as formatNumber } from '@/domain/tools'

  defineProps<{
    tool: Tool
  }>()

  const { t } = useI18n()
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .tool-info {
    .tool-header {
      display: flex;
      gap: @spacing-md;
      margin-bottom: @spacing-lg;
      flex-wrap: wrap;
    }

    .tool-icon {
      width: 64px;
      height: 64px;
      border-radius: @border-radius-lg;
      background: @accent-color-light;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 32px;
      color: @accent-color;
      flex-shrink: 0;
    }

    .tool-meta {
      flex: 1;
      min-width: 200px;
    }

    .overview-title {
      font-size: @font-size-lg;
      font-weight: @font-weight-semibold;
      margin-bottom: @spacing-sm;
    }

    .tool-tags {
      display: flex;
      gap: @spacing-xs;
      flex-wrap: wrap;
    }

    .tool-description {
      color: @text-color-light-secondary;
      font-size: @font-size-md;
      margin-bottom: @spacing-lg;
      line-height: @line-height-loose;
    }

    .tool-stats {
      display: flex;
      gap: @spacing-lg;
      flex-wrap: wrap;
      margin-bottom: @spacing-lg;
    }

    .stat-item {
      display: flex;
      align-items: center;
      gap: @spacing-xs;
      color: @text-color-light-tertiary;
    }

    .tool-changelog {
      margin-top: @spacing-lg;
      padding-top: @spacing-lg;
      border-top: 1px solid @border-color-light;

      h3 {
        font-size: @font-size-md;
        font-weight: @font-weight-semibold;
        margin-bottom: @spacing-sm;
      }

      p {
        color: @text-color-light-secondary;
        font-size: @font-size-sm;
      }
    }
  }

  @media (max-width: @screen-md) {
    .tool-info .tool-header {
      align-items: flex-start;
    }
  }
</style>
