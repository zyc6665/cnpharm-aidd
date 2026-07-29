<template>
  <section class="inspector-section">
    <div class="section-title">{{ t('workflow.inspector.taskResult') }}</div>
    <div v-if="node.type === 'tool'" class="result-actions">
      <a-button size="small" type="primary" :disabled="!canRerun" @click="$emit('run-node', node.id)">{{ t('workflow.inspector.rerunCurrentNode') }}</a-button>
      <a-button size="small" :disabled="!task" @click="$emit('rerun-downstream', node.id)">{{ t('workflow.inspector.rerunDownstream') }}</a-button>
      <a-button size="small" :disabled="!task" @click="$emit('view-task-detail', node.id)">{{ t('workflow.inspector.viewTaskDetail') }}</a-button>
    </div>
    <div v-if="task" class="task-result"><span class="task-id">{{ task.id }}</span><a-tag>{{ task.status }}</a-tag><a-progress v-if="task.status === 'running' || task.status === 'pending'" :percent="task.progress ?? 0" size="small" /><p v-if="task.error_message" class="task-error">{{ task.error_message }}</p></div>
    <a-empty v-else :description="t('workflow.inspector.noTaskResult')" />
  </section>
  <section class="inspector-section">
    <div class="section-title">{{ t('workflow.inspector.outputFiles') }}</div>
    <div v-if="outputArtifacts.length" class="output-artifact-list"><div v-for="artifact in outputArtifacts" :key="artifact.id" class="output-artifact-item"><span><strong>{{ artifact.filename }}</strong><small>{{ artifact.semantic_type || t('workflow.inspector.artifactFallback') }}</small></span><a-button size="small" @click="download(artifact)">{{ t('workflow.inspector.downloadOutput') }}</a-button></div></div>
    <a-empty v-else :description="t('workflow.inspector.noOutputFiles')" />
  </section>
</template>
<script setup lang="ts">
import { computed } from 'vue'
import { message } from 'ant-design-vue'
import { useI18n } from 'vue-i18n'
import type { ArtifactFile } from '@/types/models'
import type { WorkflowTaskRef } from '@/workflow/artifact-types'
import type { WorkflowCanvasNode } from '@/workflow/template-types'
import { triggerProtectedFileDownload } from '@/utils/protected-file-access'
const props = defineProps<{ node: WorkflowCanvasNode; task?: WorkflowTaskRef | null; artifacts?: ArtifactFile[]; selectedToolSlug?: string | null }>()
defineEmits<{ (event: 'run-node', nodeId: string): void; (event: 'rerun-downstream', nodeId: string): void; (event: 'view-task-detail', nodeId: string): void }>()
const { t } = useI18n()
const canRerun = computed(() => Boolean(props.selectedToolSlug || props.node.recommendedToolSlug || props.node.toolSlugs?.[0]))
const outputArtifacts = computed(() => props.task?.id ? (props.artifacts ?? []).filter(artifact => artifact.task_id === props.task?.id) : [])
async function download(artifact: ArtifactFile) { try { await triggerProtectedFileDownload({ url: artifact.download_url, filename: artifact.filename, original_name: artifact.filename }) } catch (error) { message.error(error instanceof Error ? error.message : t('common.error')) } }
</script>
