<template>
  <section class="workflow-results-sidebar">
    <a-tabs class="workflow-results-sidebar__tabs" size="small">
      <a-tab-pane key="node" :tab="t('workflow.resultsSidebar.tabs.node')">
        <slot name="node" />
      </a-tab-pane>
      <a-tab-pane key="inputs" :tab="t('workflow.resultsSidebar.tabs.inputs')">
        <slot name="inputs" />
      </a-tab-pane>
      <a-tab-pane key="preflight" :tab="t('workflow.resultsSidebar.tabs.preflight')">
        <slot name="preflight" />
      </a-tab-pane>
      <a-tab-pane key="report" :tab="t('workflow.resultsSidebar.tabs.report')">
        <slot name="report" />
      </a-tab-pane>
      <a-tab-pane key="artifacts" :tab="t('workflow.resultsSidebar.tabs.artifacts')">
        <slot name="artifacts" />
      </a-tab-pane>
      <a-tab-pane key="history" :tab="t('workflow.resultsSidebar.tabs.history')">
        <slot name="history" />
      </a-tab-pane>
    </a-tabs>
  </section>
</template>

<script setup lang="ts">
import { useI18n } from 'vue-i18n'

const { t } = useI18n()
</script>

<style scoped lang="less">
@import '@/assets/styles/variables.less';

.workflow-results-sidebar {
  min-height: 0;
  height: 100%;
  display: flex;
  flex-direction: column;
  background: @bg-surface;
}

.workflow-results-sidebar__tabs {
  min-height: 0;
  flex: 1;
  display: flex;
  flex-direction: column;
}

.workflow-results-sidebar__tabs :deep(.ant-tabs-nav) {
  flex: 0 0 auto;
  margin: 0;
  padding: 0 @spacing-sm;
  background: @bg-surface;
  border-bottom: 1px solid @border-color-light;
}

.workflow-results-sidebar__tabs :deep(.ant-tabs-content-holder) {
  min-height: 0;
  flex: 1;
  overflow: hidden;
}

.workflow-results-sidebar__tabs :deep(.ant-tabs-content),
.workflow-results-sidebar__tabs :deep(.ant-tabs-tabpane) {
  height: 100%;
  min-height: 0;
}

.workflow-results-sidebar__tabs :deep(.ant-tabs-tabpane) {
  overflow: auto;
  padding: @spacing-sm;
}
</style>
