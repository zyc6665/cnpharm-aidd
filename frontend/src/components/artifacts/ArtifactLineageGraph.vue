<template>
  <section class="artifact-lineage-graph">
    <div class="lineage-summary">
      <article v-for="item in summaryCards" :key="item.label">
        <strong>{{ item.value }}</strong>
        <span>{{ item.label }}</span>
      </article>
    </div>

    <div v-if="graph.nodes.length" class="lineage-grid">
      <section
        v-for="group in nodeGroups"
        :key="group.kind"
        class="lineage-group"
      >
        <h3>{{ group.title }}</h3>
        <article
          v-for="node in group.nodes"
          :key="node.id"
          class="artifact-lineage-node"
          :class="`is-${node.kind}`"
        >
          <span class="node-kind">{{ node.kind }}</span>
          <strong>{{ node.label }}</strong>
          <small v-if="node.standard_type">{{ formatStandardType(node) }}</small>
          <small v-if="node.version_id">version_id: {{ shortId(node.version_id) }}</small>
          <small v-if="node.task_id">task: {{ shortId(node.task_id) }}</small>
          <small v-if="node.workflow_node_id">workflow node: {{ node.workflow_node_id }}</small>
          <small v-if="node.tool_slug">{{ node.tool_slug }}</small>
          <a-tag v-if="node.status" :color="statusColor(node.status)">{{ node.status }}</a-tag>
        </article>
      </section>
    </div>

    <section v-if="graph.edges.length" class="lineage-edges">
      <h3>关系边</h3>
      <div
        v-for="edge in graph.edges"
        :key="edge.id"
        class="artifact-lineage-edge"
        :class="`is-${edge.kind}`"
      >
        <a-tag :color="edgeColor(edge.kind)">{{ edge.kind }}</a-tag>
        <span>{{ edgeLabel(edge.source) }}</span>
        <span class="edge-arrow">→</span>
        <span>{{ edgeLabel(edge.target) }}</span>
      </div>
    </section>

    <a-empty v-if="!graph.nodes.length" description="暂无 Artifact 谱系数据" />
  </section>
</template>

<script setup lang="ts">
  import { computed } from 'vue'
  import type {
    ArtifactLineageGraph,
    ArtifactLineageGraphEdge,
    ArtifactLineageGraphEdgeKind,
    ArtifactLineageGraphNode,
    ArtifactLineageGraphNodeKind
  } from '@/types/artifacts'

  const props = defineProps<{
    graph: ArtifactLineageGraph
  }>()

  const groupTitles: Record<ArtifactLineageGraphNodeKind, string> = {
    artifact: '标准产物',
    version: '版本',
    task: '来源任务',
    workflow_node: 'Workflow 节点'
  }

  const summaryCards = computed(() => [
    { label: '标准产物', value: props.graph.summary.artifacts },
    { label: '版本', value: props.graph.summary.versions },
    { label: '来源任务', value: props.graph.summary.tasks },
    { label: 'Workflow 节点', value: props.graph.summary.workflow_nodes },
    { label: '谱系关系', value: props.graph.summary.lineage_edges }
  ])

  const nodeGroups = computed(() => {
    return (Object.keys(groupTitles) as ArtifactLineageGraphNodeKind[])
      .map(kind => ({
        kind,
        title: groupTitles[kind],
        nodes: props.graph.nodes.filter(node => node.kind === kind)
      }))
      .filter(group => group.nodes.length > 0)
  })

  const nodesById = computed(() => {
    return Object.fromEntries(props.graph.nodes.map(node => [node.id, node]))
  })

  function edgeLabel(nodeId: string): string {
    const node = nodesById.value[nodeId]
    if (!node) return nodeId
    if (node.kind === 'version' && node.filename) {
      return `${node.filename} v${node.version ?? '-'}`
    }
    if (node.kind === 'workflow_node' && node.workflow_node_id) {
      return node.workflow_node_id
    }
    return node.label
  }

  function formatStandardType(node: ArtifactLineageGraphNode): string {
    return `${node.standard_type}@${node.standard_version ?? 1}`
  }

  function shortId(value: string): string {
    return value.length > 8 ? value.slice(0, 8) : value
  }

  function statusColor(status: string): string {
    if (status === 'SUCCESS' || status === 'available') return 'green'
    if (status === 'FAILURE') return 'red'
    if (status === 'PENDING' || status === 'RUNNING') return 'blue'
    return 'default'
  }

  function edgeColor(kind: ArtifactLineageGraphEdge['kind'] | ArtifactLineageGraphEdgeKind): string {
    if (kind === 'derived_from') return 'purple'
    if (kind === 'produced_by') return 'green'
    if (kind === 'runs_task') return 'blue'
    return 'default'
  }
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .artifact-lineage-graph {
    display: grid;
    gap: @spacing-lg;
  }

  .lineage-summary {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
    gap: @spacing-sm;
  }

  .lineage-summary article {
    padding: @spacing-md;
    border: 1px solid @border-color;
    border-radius: @border-radius-md;
    background: @bg-elevated;
  }

  .lineage-summary strong {
    display: block;
    color: @text-primary;
    font-size: @font-size-xl;
  }

  .lineage-summary span {
    color: @text-tertiary;
    font-size: @font-size-sm;
  }

  .lineage-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(230px, 1fr));
    gap: @spacing-md;
    align-items: start;
  }

  .lineage-group {
    min-width: 0;
    display: grid;
    gap: @spacing-sm;
  }

  .lineage-group h3,
  .lineage-edges h3 {
    margin: 0;
    color: @text-primary;
    font-size: @font-size-md;
  }

  .artifact-lineage-node {
    min-width: 0;
    display: grid;
    gap: 4px;
    padding: @spacing-sm;
    border: 1px solid @border-color;
    border-left: 4px solid @primary-color;
    border-radius: @border-radius-md;
    background: @bg-surface;
  }

  .artifact-lineage-node.is-version {
    border-left-color: @success-color;
  }

  .artifact-lineage-node.is-task {
    border-left-color: @warning-color;
  }

  .artifact-lineage-node.is-workflow_node {
    border-left-color: @accent-color;
  }

  .artifact-lineage-node strong,
  .artifact-lineage-node small {
    overflow-wrap: anywhere;
  }

  .artifact-lineage-node small,
  .node-kind {
    color: @text-tertiary;
    font-size: @font-size-xs;
  }

  .node-kind {
    font-weight: @font-weight-bold;
    text-transform: uppercase;
  }

  .lineage-edges {
    display: grid;
    gap: @spacing-sm;
  }

  .artifact-lineage-edge {
    min-width: 0;
    display: grid;
    grid-template-columns: auto minmax(0, 1fr) auto minmax(0, 1fr);
    gap: @spacing-sm;
    align-items: center;
    padding: @spacing-sm;
    border: 1px solid @border-color;
    border-radius: @border-radius-md;
    background: @bg-elevated;
  }

  .artifact-lineage-edge span {
    overflow-wrap: anywhere;
  }

  .edge-arrow {
    color: @text-tertiary;
  }

  @media (max-width: @screen-sm) {
    .artifact-lineage-edge {
      grid-template-columns: minmax(0, 1fr);
    }
  }
</style>
