<template>
  <main class="project-lineage-page">
    <router-link :to="`/projects/${projectId}`" class="back-link">返回项目总览</router-link>
    <ProjectWorkspaceNav :project-id="projectId" />

    <AppPageHeader
      title="Artifact 谱系"
      subtitle="追踪标准产物、版本、来源任务和 Workflow 节点关系"
    >
      <template #actions>
        <a-button :loading="loading" @click="load">刷新谱系</a-button>
      </template>
    </AppPageHeader>

    <a-alert
      v-if="lineageLoadError"
      class="lineage-alert"
      type="error"
      show-icon
      message="Artifact 谱系加载失败"
    >
      <template #action><a-button size="small" @click="load">重试</a-button></template>
    </a-alert>

    <a-skeleton v-if="loading && !graph" active :paragraph="{ rows: 8 }" />
    <ArtifactLineageGraph v-else-if="graph" :graph="graph" />
  </main>
</template>

<script setup lang="ts">
  import { computed, onMounted, ref } from 'vue'
  import { useRoute } from 'vue-router'
  import { getProjectArtifactLineage } from '@/api/artifacts'
  import ArtifactLineageGraph from '@/components/artifacts/ArtifactLineageGraph.vue'
  import AppPageHeader from '@/components/common/AppPageHeader.vue'
  import ProjectWorkspaceNav from '@/components/projects/ProjectWorkspaceNav.vue'
  import type { ArtifactLineageGraph as ArtifactLineageGraphData } from '@/types/artifacts'

  const route = useRoute()
  const projectId = computed(() => String(route.params.projectId || ''))
  const graph = ref<ArtifactLineageGraphData | null>(null)
  const loading = ref(false)
  const lineageLoadError = ref(false)

  async function load() {
    if (!projectId.value) return
    loading.value = true
    lineageLoadError.value = false
    try {
      graph.value = (await getProjectArtifactLineage(projectId.value)).data
    } catch {
      lineageLoadError.value = true
    } finally {
      loading.value = false
    }
  }

  onMounted(() => {
    void load()
  })
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .project-lineage-page {
    max-width: @page-max-width;
    margin: 0 auto;
    padding: @spacing-xl @spacing-lg @spacing-xxl;
  }

  .back-link {
    display: inline-block;
    margin-bottom: @spacing-lg;
    color: @text-tertiary;
  }

  .lineage-alert {
    margin-bottom: @spacing-lg;
  }
</style>
