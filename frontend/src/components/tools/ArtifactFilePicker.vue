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
        <span class="artifact-toolbar-label">{{ t('tools.selectArtifact') }}</span>
        <a-button type="link" size="small" :loading="artifactsStore.loading" @click="refreshArtifacts">
          {{ t('common.refresh') }}
        </a-button>
      </div>
      <a-select
        :value="selectedArtifact?.id"
        :options="artifactOptions"
        :loading="artifactsStore.loading"
        :placeholder="t('tools.noArtifacts')"
        show-search
        allow-clear
        @change="handleArtifactSelect"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
  import { computed, onMounted, ref, watch } from 'vue'
  import { useI18n } from 'vue-i18n'
  import type { UploadFile } from 'ant-design-vue'
  import { UploadOutlined } from '@ant-design/icons-vue'
  import { useArtifactsStore } from '@/stores'
  import type { ArtifactFile } from '@/types/models'

  const props = withDefaults(
    defineProps<{
      uploadList: UploadFile[]
      selectedArtifact?: ArtifactFile | null
      accept?: string
      allowArtifacts?: boolean
    }>(),
    {
      selectedArtifact: null,
      accept: undefined,
      allowArtifacts: true
    }
  )

  const emit = defineEmits<{
    'update:uploadList': [files: UploadFile[]]
    'update:selectedArtifact': [artifact: ArtifactFile | null]
  }>()

  const { t } = useI18n()
  const artifactsStore = useArtifactsStore()
  const sourceMode = ref<'upload' | 'artifact'>('upload')

  const artifactOptions = computed(() => {
    return artifactsStore.items.map((artifact) => ({
      label: artifact.filename,
      value: artifact.id
    }))
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

    const artifact = artifactsStore.items.find((item) => item.id === artifactId) ?? null
    emit('update:selectedArtifact', artifact)
    emit('update:uploadList', [])
  }

  watch(
    () => [props.selectedArtifact, props.allowArtifacts] as const,
    () => {
      syncSourceMode()
    },
    { immediate: true }
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
    color: @text-color-secondary;
    font-size: @font-size-sm;
  }
</style>
