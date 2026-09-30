<template>
  <div class="standard-artifact-inputs">
    <a-form-item
      v-for="slot in slots"
      :key="slot.name"
      :label="slot.title || standardArtifactTypeLabel(slot.type) || slot.name"
      :required="slot.required"
      :extra="slot.description"
    >
      <div class="standard-artifact-input-control">
        <a-select
          v-if="currentProjectId"
          :value="selectedArtifacts[slot.name]?.latest_version.id"
          :loading="loading"
          allow-clear
          show-search
          option-filter-prop="label"
          :placeholder="projectArtifactPlaceholder"
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
              <small>{{ artifact.latest_version.filename }} · v{{ artifact.latest_version.version }}</small>
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
  import { useI18n } from 'vue-i18n'
  import type { TypedArtifact } from '@/types/artifacts'
  import {
    filterCompatibleProjectArtifacts,
    formatStandardArtifactLabel,
    getStandardArtifactTypeLabelKey,
    getStandardInputAccept,
    type StandardArtifactInputSlot,
  } from '@/domain/tools'
  import ArtifactFilePicker from './ArtifactFilePicker.vue'

  const { t } = useI18n()

  const props = withDefaults(
    defineProps<{
      slots: readonly StandardArtifactInputSlot[]
      currentProjectId?: string
      projectArtifacts: readonly TypedArtifact[]
      loading?: boolean
      selectedArtifacts: Record<string, TypedArtifact | undefined>
      uploadLists: Record<string, UploadFile[]>
      projectArtifactPlaceholder?: string
      toolSlug?: string | null
    }>(),
    {
      currentProjectId: undefined,
      loading: false,
      projectArtifactPlaceholder: 'Select a project file',
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

  const standardArtifactTypeLabel = (type: string) => {
    const key = getStandardArtifactTypeLabelKey(type)
    return key ? t(key) : undefined
  }

  const selectArtifact = (slotName: string, value: unknown) => {
    emit('select-artifact', slotName, typeof value === 'string' ? value : undefined)
  }
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .standard-artifact-inputs {
    margin-bottom: @spacing-md;

    :deep(.ant-form-item:last-child) {
      margin-bottom: 0;
    }
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
