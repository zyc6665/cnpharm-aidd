<template>
  <section class="workflow-preflight-panel">
    <div class="preflight-header">
      <div>
        <span class="preflight-kicker">运行前检查</span>
        <h3>{{ preflight.primaryMessage }}</h3>
      </div>
      <a-space size="small" wrap>
        <a-tag color="green">可运行 {{ preflight.runnableCount }}</a-tag>
        <a-tag color="orange">阻塞 {{ preflight.blockedCount }}</a-tag>
        <a-tag color="blue">完成 {{ preflight.completedCount }}</a-tag>
        <a-tag v-if="preflight.failedCount" color="red">失败 {{ preflight.failedCount }}</a-tag>
      </a-space>
    </div>

    <div class="preflight-body">
      <div class="preflight-summary">
        <strong>流程运行建议</strong>
        <p>{{ summaryHint }}</p>
      </div>

      <div class="preflight-issues">
        <div v-if="preflight.issues.length === 0" class="preflight-empty">
          当前没有阻塞问题，可以继续运行可执行节点。
        </div>
        <div
          v-for="issue in preflight.issues"
          :key="issue.id"
          class="preflight-issue"
          :class="`is-${issue.severity}`"
        >
          <div class="issue-copy">
            <span class="issue-node">{{ issue.nodeTitle }}</span>
            <strong>{{ issue.title }}</strong>
            <p>{{ issue.detail }}</p>
          </div>
          <a-button size="small" @click="$emit('select-node', issue.nodeId)">
            查看节点
          </a-button>
        </div>
      </div>
    </div>

    <div class="preflight-actions">
      <a-button
        type="primary"
        :disabled="!preflight.canRun"
        :loading="running"
        @click="$emit('run-ready-nodes')"
      >
        运行可执行节点
      </a-button>
      <span class="preflight-action-hint">
        会按依赖顺序运行已满足输入条件的节点，遇到失败会暂停。
      </span>
    </div>
  </section>
</template>

<script setup lang="ts">
  import { computed } from 'vue'
  import type { WorkflowPreflightSummary } from '@/workflow/preflight'

  const props = defineProps<{
    preflight: WorkflowPreflightSummary
    running?: boolean
  }>()

  defineEmits<{
    (event: 'run-ready-nodes'): void
    (event: 'select-node', nodeId: string): void
  }>()

  const summaryHint = computed(() => {
    if (props.preflight.runningCount > 0) {
      return '已有节点正在运行，建议等待当前任务结束后再继续。'
    }
    if (props.preflight.runnableCount > 0 && props.preflight.blockedCount > 0) {
      return '可以先运行已就绪节点，阻塞节点会在上游产物生成后自动进入可运行状态。'
    }
    if (props.preflight.runnableCount > 0) {
      return '当前已有节点满足运行条件，可以启动流程推进。'
    }
    return '请先补齐工具选择、输入文件或上游产物，再启动流程。'
  })
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .workflow-preflight-panel {
    border: 1px solid rgba(24, 144, 255, 0.12);
    border-radius: @border-radius-md;
    background: rgba(255, 255, 255, 0.96);
    box-shadow: @shadow-sm;
    overflow: hidden;
  }

  .preflight-header,
  .preflight-actions {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: @spacing-md;
    padding: @spacing-md @spacing-lg;
  }

  .preflight-header {
    border-bottom: 1px solid @border-color-light;
  }

  .preflight-kicker {
    color: @text-color-light-tertiary;
    font-size: @font-size-xs;
    font-weight: 800;
  }

  .preflight-header h3 {
    margin: 2px 0 0;
    color: @text-color-light-primary;
    font-size: @font-size-lg;
    font-weight: 800;
  }

  .preflight-body {
    display: grid;
    grid-template-columns: minmax(220px, 0.32fr) minmax(0, 1fr);
    gap: @spacing-md;
    padding: @spacing-lg;
  }

  .preflight-summary {
    padding: @spacing-md;
    border-radius: @border-radius-sm;
    background: @bg-light-secondary;
  }

  .preflight-summary strong {
    color: @text-color-light-primary;
    font-size: @font-size-md;
  }

  .preflight-summary p,
  .preflight-action-hint,
  .issue-copy p {
    margin: 4px 0 0;
    color: @text-color-light-secondary;
    font-size: @font-size-md;
    line-height: 1.5;
  }

  .preflight-issues {
    display: grid;
    gap: @spacing-sm;
  }

  .preflight-empty,
  .preflight-issue {
    min-height: 68px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: @spacing-md;
    padding: @spacing-md;
    border: 1px solid @border-color-light;
    border-radius: @border-radius-sm;
    background: #fff;
  }

  .preflight-empty {
    justify-content: flex-start;
    color: @success-color;
    font-weight: 700;
  }

  .preflight-issue.is-error {
    border-color: rgba(255, 77, 79, 0.22);
    background: rgba(255, 77, 79, 0.04);
  }

  .preflight-issue.is-warning {
    border-color: rgba(250, 173, 20, 0.28);
    background: rgba(250, 173, 20, 0.06);
  }

  .preflight-issue.is-info {
    border-color: rgba(24, 144, 255, 0.2);
    background: rgba(24, 144, 255, 0.05);
  }

  .issue-copy {
    min-width: 0;
  }

  .issue-node {
    display: block;
    color: @text-color-light-tertiary;
    font-size: @font-size-xs;
    font-weight: 700;
  }

  .issue-copy strong {
    color: @text-color-light-primary;
    font-size: @font-size-sm;
  }

  .preflight-actions {
    border-top: 1px solid @border-color-light;
    background: @bg-light-secondary;
  }

  @media (max-width: 960px) {
    .preflight-body {
      grid-template-columns: 1fr;
    }

    .preflight-header,
    .preflight-actions,
    .preflight-issue {
      align-items: flex-start;
      flex-direction: column;
    }
  }
</style>
