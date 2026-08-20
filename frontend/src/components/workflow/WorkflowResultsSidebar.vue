<template>
  <section class="workflow-results-sidebar">
    <a-tabs class="workflow-results-sidebar__tabs" size="small">
      <a-tab-pane key="node" tab="节点结果">
        <slot name="node" />
      </a-tab-pane>
      <a-tab-pane key="inputs" tab="运行配置">
        <slot name="inputs" />
      </a-tab-pane>
      <a-tab-pane key="preflight" tab="预检">
        <slot name="preflight" />
      </a-tab-pane>
      <a-tab-pane key="report" tab="结果报告">
        <slot name="report" />
      </a-tab-pane>
      <a-tab-pane key="artifacts" tab="产物">
        <slot name="artifacts" />
      </a-tab-pane>
      <a-tab-pane key="history" tab="历史">
        <slot name="history" />
      </a-tab-pane>
    </a-tabs>
  </section>
</template>

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
