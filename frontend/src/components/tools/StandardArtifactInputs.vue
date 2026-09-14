<template>
  <div class="standard-artifact-inputs">
    <div class="standard-artifact-inputs__header">
      <span>标准 Artifact 输入</span>
      <a-tag color="blue">Tool Package v2</a-tag>
    </div>

    <a-alert
      v-if="!currentProjectId"
      type="info"
      show-icon
      message="可直接上传文件运行；如需复用项目 Artifact，请从项目内进入工具或在 URL 带 project_id。"
    />
    <a-alert
      v-else-if="!loading && projectArtifacts.length === 0"
      type="info"
      show-icon
      message="当前项目暂无可绑定的标准 Artifact。"
    />

    <a-form-item
      v-for="slot in slots"
      :key="slot.name"
      :label="slot.name"
      :required="slot.required"
      :extra="`标准类型：${slot.type}`"
    >
      <div class="standard-artifact-input-control">
        <a-select
          v-if="currentProjectId"
          :value="selectedArtifacts[slot.name]?.latest_version.id"
          :loading="loading"
          allow-clear
          show-search
          option-filter-prop="label"
          placeholder="选择项目中的兼容 ArtifactVersion"
          @change="selectArtifact(slot.name, $event)"
        >
          <a-select-option
            v-for="artifact in compatibleArtifacts(slot)"
            :key="artifact.latest_version.id"
            :value="artifact.latest_version.id"
            :label="formatStandardArtifactLabel(artifact)"
          >
            <div class="standard-artifact-option">
              <span>{{ artifact.name || artifact.latest_version.filename }}</span>
              <small>{{ artifact.semantic_type }} · v{{ artifact.latest_version.version }}</small>
            </div>
          </a-select-option>
        </a-select>
        <ArtifactFilePicker
          :upload-list="uploadLists[slot.name] ?? []"
          :selected-artifact="null"
          :accept="getStandardInputAccept(slot)"
          :allow-artifacts="false"
          :allow-uploads="true"
          :current-tool-slug="toolSlug"
          @update:upload-list="(files) => emit('update-upload-list', slot.name, files)"
        />
      </div>
    </a-form-item>
  </div>
</template>

<script setup lang="ts">
  import type { UploadFile } from 'ant-design-vue'
  import type { TypedArtifact } from '@/types/artifacts'
  import {
    filterCompatibleProjectArtifacts,
    formatStandardArtifactLabel,
    getStandardInputAccept,
    type StandardArtifactInputSlot,
  } from '@/domain/tools'
  import ArtifactFilePicker from './ArtifactFilePicker.vue'

  const props = withDefaults(
    defineProps<{
      slots: readonly StandardArtifactInputSlot[]
      currentProjectId?: string
      projectArtifacts: readonly TypedArtifact[]
      loading?: boolean
      selectedArtifacts: Record<string, TypedArtifact | undefined>
      uploadLists: Record<string, UploadFile[]>
      toolId?: string | null
      toolSlug?: string | null
    }>(),
    {
      currentProjectId: undefined,
      loading: false,
      toolId: null,
      toolSlug: null,
    }
  )

  const emit = defineEmits<{
    'select-artifact': [slotName: string, versionId: string | undefined]
    'update-upload-list': [slotName: string, files: UploadFile[]]
  }>()

  const compatibleArtifacts = (slot: StandardArtifactInputSlot) => {
    return filterCompatibleProjectArtifacts(slot, props.projectArtifacts)
  }

  const selectArtifact = (slotName: string, value: unknown) => {
    emit('select-artifact', slotName, typeof value === 'string' ? value : undefined)
  }
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .standard-artifact-inputs {
    margin-bottom: @spacing-lg;
    padding: @spacing-md;
    border: 1px solid @accent-color-border;
    border-radius: @border-radius-base;
    background: @accent-color-light;

    :deep(.ant-alert) {
      margin-bottom: @spacing-md;
    }

    :deep(.ant-form-item:last-child) {
      margin-bottom: 0;
    }
  }

  .standard-artifact-inputs__header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: @spacing-sm;
    margin-bottom: @spacing-md;
    font-weight: @font-weight-semibold;
    color: @text-primary;
  }

  .standard-artifact-input-control {
    display: flex;
    flex-direction: column;
    gap: @spacing-sm;
  }

  .standard-artifact-option {
    display: flex;
    flex-direction: column;
    gap: 2px;

    small {
      color: @text-color-light-tertiary;
      font-size: @font-size-sm;
    }
  }
</style>
