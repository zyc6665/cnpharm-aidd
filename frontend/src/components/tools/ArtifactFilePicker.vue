<template>
  <div class="artifact-file-picker">
    <a-radio-group
      v-if="allowArtifacts"
      :value="sourceMode"
      size="small"
      class="source-switch"
      @update:value="handleSourceModeChange"
    >
      <a-radio-button value="upload">{{ t('tools.fileSourceUpload') }}</a-radio-button>
      <a-radio-button value="artifact">{{ t('tools.fileSourceArtifact') }}</a-radio-button>
    </a-radio-group>

    <div v-if="sourceMode === 'upload' || !allowArtifacts" class="source-panel">
      <a-upload
        :file-list="uploadList"
        :accept="accept"
        :before-upload="() => false"
        :max-count="1"
        @update:file-list="handleUploadListChange"
      >
        <a-button>
          <UploadOutlined />
          {{ t('tools.selectFile') }}
        </a-button>
      </a-upload>
    </div>

    <div v-else class="source-panel artifact-panel">
      <div class="artifact-toolbar">
        <span class="artifact-toolbar-label">{{ t('tools.selectCompatibleArtifact') }}</span>
        <a-button type="link" size="small" :loading="artifactsStore.loading" @click="refreshArtifacts">
          {{ t('common.refresh') }}
        </a-button>
      </div>
      <div
        v-if="artifactTaskGroups.length > 0"
        class="artifact-cascade"
      >
        <a-select
          class="artifact-task-select"
          :value="selectedTaskId"
          :loading="artifactsStore.loading"
          :placeholder="t('tools.selectArtifactTask')"
          show-search
          option-filter-prop="label"
          @change="handleTaskSelect"
        >
          <a-select-option
            v-for="taskGroup in artifactTaskGroups"
            :key="taskGroup.taskId"
            :value="taskGroup.taskId"
            :label="`${taskGroup.taskId} ${taskGroup.toolName}`"
          >
            <div class="artifact-task-option-label">
              <span class="artifact-task-option-main">#{{ taskGroup.taskId }}</span>
              <span class="artifact-task-option-sub">{{ taskGroup.toolName }}</span>
              <a-tag class="artifact-task-option-count">
                {{ t('workflow.artifacts.taskCount', { count: taskGroup.artifacts.length }) }}
              </a-tag>
            </div>
          </a-select-option>
        </a-select>
        <a-select
          class="artifact-file-select"
          :value="selectedArtifact?.id"
          :loading="artifactsStore.loading"
          :placeholder="t('tools.noArtifacts')"
          show-search
          allow-clear
          option-filter-prop="label"
          @change="handleArtifactSelect"
        >
          <a-select-option
            v-for="artifact in selectedTaskArtifacts"
            :key="artifact.id"
            :value="artifact.id"
            :label="`${artifact.filename} ${selectedTaskGroup?.toolName ?? ''} ${selectedTaskId ?? ''}`"
          >
            <div class="artifact-option">
              <span class="artifact-option-name">{{ artifact.filename }}</span>
              <span class="artifact-option-meta">{{ formatArtifactMeta(artifact) }}</span>
            </div>
          </a-select-option>
        </a-select>
      </div>
      <a-empty
        v-else
        class="artifact-empty"
        :description="t('tools.noCompatibleArtifacts')"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
  import { computed, onMounted, ref, watch } from 'vue'
  import { useI18n } from 'vue-i18n'
  import dayjs from 'dayjs'
  import type { UploadFile } from 'ant-design-vue'
  import { UploadOutlined } from '@ant-design/icons-vue'
  import { useArtifactsStore } from '@/stores'
  import type { ArtifactFile } from '@/types/models'
  import { groupCompatibleArtifactsByTask } from './artifact-selection'

  const props = withDefaults(
    defineProps<{
      uploadList: UploadFile[]
      selectedArtifact?: ArtifactFile | null
      accept?: string
      allowArtifacts?: boolean
      currentToolId?: string | null
      currentToolSlug?: string | null
    }>(),
    {
      selectedArtifact: null,
      accept: undefined,
      allowArtifacts: true,
      currentToolId: null,
      currentToolSlug: null
    }
  )

  const emit = defineEmits<{
    'update:uploadList': [files: UploadFile[]]
    'update:selectedArtifact': [artifact: ArtifactFile | null]
  }>()

  const { t } = useI18n()
  const artifactsStore = useArtifactsStore()
  const sourceMode = ref<'upload' | 'artifact'>('upload')
  const selectedTaskId = ref<string>()

  const artifactTaskGroups = computed(() => {
    return groupCompatibleArtifactsByTask(artifactsStore.items, props.accept, {
      toolId: props.currentToolId,
      toolSlug: props.currentToolSlug
    })
  })

  const selectedTaskGroup = computed(() => {
    return artifactTaskGroups.value.find((group) => group.taskId === selectedTaskId.value) ?? null
  })

  const selectedTaskArtifacts = computed(() => {
    return selectedTaskGroup.value?.artifacts ?? []
  })

  const compatibleArtifacts = computed(() => {
    return artifactTaskGroups.value.flatMap((group) => group.artifacts)
  })

  function syncSourceMode() {
    if (!props.allowArtifacts) {
      sourceMode.value = 'upload'
      return
    }

    if (props.selectedArtifact) {
      sourceMode.value = 'artifact'
      return
    }

    sourceMode.value = 'upload'
  }

  async function refreshArtifacts() {
    if (!props.allowArtifacts) {
      return
    }
    await artifactsStore.fetchArtifacts({ page: 1, page_size: 100 })
  }

  function handleSourceModeChange(value: 'upload' | 'artifact') {
    sourceMode.value = value
    if (value === 'upload') {
      emit('update:selectedArtifact', null)
      return
    }

    emit('update:uploadList', [])
    syncSelectedTask()
  }

  function handleUploadListChange(files: UploadFile[]) {
    emit('update:uploadList', files)
    if (files.length > 0) {
      emit('update:selectedArtifact', null)
    }
  }

  function handleArtifactSelect(artifactId: string | undefined) {
    if (!artifactId) {
      emit('update:selectedArtifact', null)
      return
    }

    const artifact = selectedTaskArtifacts.value.find((item) => item.id === artifactId) ?? null
    emit('update:selectedArtifact', artifact)
    emit('update:uploadList', [])
  }

  function handleTaskSelect(taskId: string) {
    selectedTaskId.value = taskId
    if (props.selectedArtifact?.task_id !== taskId) {
      emit('update:selectedArtifact', null)
    }
    emit('update:uploadList', [])
  }

  function formatArtifactMeta(artifact: ArtifactFile): string {
    return `${artifact.tool_name} · ${dayjs(artifact.created_at).format('YYYY-MM-DD HH:mm')}`
  }

  function syncSelectedTask() {
    if (!props.allowArtifacts) {
      selectedTaskId.value = undefined
      return
    }

    if (props.selectedArtifact && compatibleArtifacts.value.some((artifact) => artifact.id === props.selectedArtifact?.id)) {
      selectedTaskId.value = props.selectedArtifact.task_id
      return
    }

    if (selectedTaskId.value && artifactTaskGroups.value.some((group) => group.taskId === selectedTaskId.value)) {
      return
    }

    selectedTaskId.value = artifactTaskGroups.value[0]?.taskId
  }

  watch(
    () => [props.selectedArtifact, props.allowArtifacts] as const,
    () => {
      syncSourceMode()
    },
    { immediate: true }
  )

  watch(
    () => [
      props.selectedArtifact?.id,
      props.allowArtifacts,
      props.accept,
      props.currentToolId,
      props.currentToolSlug,
      artifactTaskGroups.value.map((group) => group.taskId).join('|')
    ] as const,
    () => {
      syncSelectedTask()
    },
    { immediate: true }
  )

  watch(
    compatibleArtifacts,
    (nextArtifacts) => {
      if (!props.selectedArtifact) {
        return
      }

      if (!nextArtifacts.some((artifact) => artifact.id === props.selectedArtifact?.id)) {
        emit('update:selectedArtifact', null)
      }
    }
  )

  onMounted(async () => {
    if (props.allowArtifacts && artifactsStore.items.length === 0) {
      await refreshArtifacts()
    }
  })
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .artifact-file-picker {
    display: flex;
    flex-direction: column;
    gap: @spacing-sm;
  }

  .source-switch {
    width: fit-content;
  }

  .source-panel {
    display: flex;
    flex-direction: column;
    gap: @spacing-sm;
  }

  .artifact-toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: @spacing-sm;
  }

  .artifact-toolbar-label {
    color: @text-color-light-secondary;
    font-size: @font-size-sm;
  }

  .artifact-select {
    width: 100%;
  }

  .artifact-cascade {
    display: grid;
    grid-template-columns: minmax(180px, 280px) minmax(0, 1fr);
    gap: @spacing-sm;
    align-items: start;
  }

  .artifact-task-select,
  .artifact-file-select {
    width: 100%;
  }

  .artifact-task-option-label {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto;
    gap: @spacing-xs @spacing-sm;
    align-items: center;
    padding: @spacing-xs 0;
  }

  .artifact-task-option-main,
  .artifact-task-option-sub {
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .artifact-task-option-main {
    color: @text-color-light-primary;
    font-family: @font-family-mono;
    font-size: @font-size-xs;
  }

  .artifact-task-option-sub {
    color: @text-color-light-secondary;
    font-size: @font-size-xs;
  }

  .artifact-task-option-count {
    grid-row: span 2;
    margin-inline-end: 0;
  }

  .artifact-option {
    display: flex;
    flex-direction: column;
    gap: @spacing-xs;
    min-width: 0;
  }

  .artifact-option-name {
    overflow: hidden;
    color: @text-color-light-primary;
    text-overflow: ellipsis;
  }

  .artifact-option-meta {
    overflow: hidden;
    color: @text-color-light-secondary;
    font-size: @font-size-xs;
    text-overflow: ellipsis;
  }

  .artifact-empty {
    padding: @spacing-md;
    border: 1px dashed #d8e1ee;
    border-radius: @border-radius-md;
    background: #fbfdff;
  }

  @media (max-width: @screen-sm) {
    .artifact-cascade {
      grid-template-columns: minmax(0, 1fr);
    }
  }
</style>
