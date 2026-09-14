<template>
  <div class="tool-sidebar">
    <div v-if="tool.tags?.length" class="tags-info card">
      <h3 class="sidebar-title">
        <TagOutlined />
        {{ t('tools.tags') }}
      </h3>
      <div class="tags-list">
        <a-tag v-for="tag in tool.tags" :key="tag.id" :color="tag.color">
          {{ tag.name }}
        </a-tag>
      </div>
    </div>

    <div class="status-info card">
      <h3 class="sidebar-title">
        <InfoCircleOutlined />
        {{ t('tools.toolInfo') }}
      </h3>
      <div class="info-list">
        <div class="info-item">
          <span class="info-label">{{ t('tools.status') }}:</span>
          <a-tag :color="getStatusColor(tool.status)">{{ tool.status }}</a-tag>
        </div>
        <div class="info-item validation-info">
          <span class="info-label">验证等级:</span>
          <a-space size="small" wrap>
            <a-tag
              v-for="badge in validationBadges"
              :key="badge.label"
              :color="badge.color"
            >
              {{ badge.label }}
            </a-tag>
          </a-space>
        </div>
        <div class="info-item">
          <span class="info-label">{{ t('common.createdAt') }}:</span>
          <span>{{ formatDate(tool.created_at) }}</span>
        </div>
        <div v-if="tool.updated_at" class="info-item">
          <span class="info-label">{{ t('common.updatedAt') }}:</span>
          <span>{{ formatDate(tool.updated_at) }}</span>
        </div>
      </div>
    </div>

    <div v-if="isRemoteToolV1" class="remote-tool-info card">
      <h3 class="sidebar-title">
        <InfoCircleOutlined />
        远程 API
      </h3>
      <div class="remote-tool-info-list">
        <div class="remote-tool-info-item">
          <span class="remote-tool-info-label">协议:</span>
          <a-tag color="blue">remote_tool_v1</a-tag>
        </div>
        <div v-if="remoteToolBaseUrl" class="remote-tool-info-item">
          <span class="remote-tool-info-label">服务:</span>
          <span class="remote-tool-info-value">{{ remoteToolBaseUrl }}</span>
        </div>
        <div v-if="remoteToolManifestHash" class="remote-tool-info-item">
          <span class="remote-tool-info-label">manifest_sha256:</span>
          <code class="remote-tool-manifest-hash">{{ remoteToolManifestHash }}</code>
        </div>
        <div class="remote-tool-info-item">
          <span class="remote-tool-info-label">smoke test:</span>
          <a-tag :color="remoteToolSmokeStatusColor(remoteToolSmokeStatus)">
            {{ remoteToolSmokeStatusText(remoteToolSmokeStatus) }}
          </a-tag>
        </div>
        <div v-if="remoteToolSmokeTaskId" class="remote-tool-info-item">
          <span class="remote-tool-info-label">任务:</span>
          <router-link :to="`/tasks/${remoteToolSmokeTaskId}`">
            查看 smoke test 任务
          </router-link>
        </div>
        <div v-if="remoteToolSmokeError" class="remote-tool-info-item">
          <span class="remote-tool-info-label">失败原因:</span>
          <span class="remote-tool-info-value">{{ remoteToolSmokeError }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
  import { useI18n } from 'vue-i18n'
  import { InfoCircleOutlined, TagOutlined } from '@ant-design/icons-vue'
  import type { Tool } from '@/types/models'
  import type { ToolValidationBadge } from '@/utils/tool-validation'
  import {
    formatToolDate as formatDate,
    getToolStatusColor as getStatusColor,
  } from '@/domain/tools'

  defineProps<{
    tool: Tool
    validationBadges: readonly ToolValidationBadge[]
    isRemoteToolV1: boolean
    remoteToolBaseUrl?: string
    remoteToolManifestHash?: string
    remoteToolSmokeStatus: string
    remoteToolSmokeTaskId?: string
    remoteToolSmokeError?: string
    remoteToolSmokeStatusColor: (status: string) => string
    remoteToolSmokeStatusText: (status: string) => string
  }>()

  const { t } = useI18n()
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .tool-sidebar {
    display: flex;
    flex-direction: column;
    gap: @spacing-lg;

    @media (min-width: @screen-lg) {
      position: sticky;
      top: @spacing-lg;
      align-self: start;
    }

    @media (max-width: @screen-lg) {
      order: -1;
    }
  }

  .card {
    background: @bg-elevated;
    border: 1px solid @border-color;
    border-radius: @border-radius-lg;
    padding: @spacing-lg;
    box-shadow: @shadow-sm;
  }

  .sidebar-title {
    font-size: @font-size-md;
    font-weight: @font-weight-semibold;
    margin-bottom: @spacing-md;
    display: flex;
    align-items: center;
    gap: @spacing-xs;
  }

  .tags-info {
    .tags-list {
      display: flex;
      flex-wrap: wrap;
      gap: @spacing-xs;
    }
  }

  .status-info {
    .info-list {
      display: flex;
      flex-direction: column;
      gap: @spacing-sm;
    }

    .info-item {
      display: flex;
      align-items: center;
      gap: @spacing-sm;
      font-size: @font-size-sm;
    }

    .info-label {
      color: @text-color-light-tertiary;
      min-width: 70px;
    }
  }

  .remote-tool-info-list {
    display: flex;
    flex-direction: column;
    gap: @spacing-sm;
  }

  .remote-tool-info-item {
    display: flex;
    align-items: flex-start;
    gap: @spacing-sm;
    font-size: @font-size-sm;
  }

  .remote-tool-info-label {
    min-width: 96px;
    color: @text-color-light-tertiary;
  }

  .remote-tool-info-value,
  .remote-tool-manifest-hash {
    flex: 1;
    min-width: 0;
    word-break: break-all;
  }

  .remote-tool-manifest-hash {
    color: @text-color-light-secondary;
    font-family: monospace;
    font-size: 12px;
  }

  @media (max-width: @screen-md) {
    .card {
      padding: @spacing-md;
    }
  }
</style>
