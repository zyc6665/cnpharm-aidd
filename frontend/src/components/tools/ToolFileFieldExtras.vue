<template>
  <div class="tool-file-field-extras">
    <div v-if="showSdfConverter" class="sdf-converter">
      <div class="sdf-converter__copy">
        <strong>SDF 转 Ligand PDB</strong>
        <span>上传一个 SDF 文件，转换后自动填入 ligand_pdb。</span>
      </div>
      <a-upload
        accept=".sdf"
        :show-upload-list="false"
        :before-upload="createSdfUploadBefore(fieldKey)"
      >
        <a-button size="small" :loading="sdfConversionLoading">
          <FileTextOutlined />
          上传 SDF 并转换
        </a-button>
      </a-upload>
    </div>
    <div
      v-if="showSdfConverter && sdfConversionStatusText"
      class="sdf-converter-status"
      :class="{ 'is-error': Boolean(sdfConversionError) }"
    >
      {{ sdfConversionStatusText }}
    </div>
    <div v-if="isFileField && exampleFile" class="example-file-binding">
      <FileTextOutlined />
      <span>{{ t('tools.exampleFileBound') }}: {{ exampleFile.filename }}</span>
      <a-button
        type="link"
        size="small"
        data-testid="clear-example-file"
        @click="emit('clear-example', fieldKey)"
      >
        {{ t('common.clear') }}
      </a-button>
    </div>
    <div v-if="isFileField && convertedFile" class="converted-file-binding">
      <FileTextOutlined />
      <span>已转换: {{ convertedFile.filename }}</span>
      <a-button
        type="link"
        size="small"
        data-testid="clear-converted-file"
        @click="emit('clear-converted', fieldKey)"
      >
        {{ t('common.clear') }}
      </a-button>
    </div>
  </div>
</template>

<script setup lang="ts">
  import { computed } from 'vue'
  import { useI18n } from 'vue-i18n'
  import { FileTextOutlined } from '@ant-design/icons-vue'
  import type { FileUploadResponse, SchemaProperty } from '@/types/models'
  import { isFileSchemaProperty } from '@/domain/tools'

  const props = defineProps<{
    fieldKey: string
    property: SchemaProperty
    showSdfConverter: boolean
    sdfConversionLoading: boolean
    sdfConversionStatusText?: string
    sdfConversionError?: string
    exampleFile?: FileUploadResponse
    convertedFile?: FileUploadResponse
    createSdfUploadBefore: (fieldKey: string) => (file: File) => boolean
  }>()

  const emit = defineEmits<{
    'clear-example': [fieldKey: string]
    'clear-converted': [fieldKey: string]
  }>()

  const { t } = useI18n()
  const isFileField = computed(() => isFileSchemaProperty(props.property))
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .tool-file-field-extras {
    display: block;
  }

  .example-file-binding {
    display: flex;
    align-items: center;
    gap: @spacing-xs;
    margin-top: @spacing-sm;
    padding: 6px 10px;
    border: 1px solid @success-color-light;
    border-radius: @border-radius-base;
    background: @success-color-light;
    color: @text-primary;
    font-size: @font-size-sm;
    flex-wrap: wrap;
  }

  .sdf-converter {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: @spacing-sm;
    margin-top: @spacing-sm;
    padding: 8px 10px;
    border: 1px solid @accent-color-border;
    border-radius: @border-radius-base;
    background: @accent-color-light;
    flex-wrap: wrap;
  }

  .sdf-converter__copy {
    display: flex;
    flex-direction: column;
    gap: 2px;
    color: @text-primary;
    font-size: @font-size-sm;
  }

  .sdf-converter-status {
    margin-top: @spacing-xs;
    color: @text-secondary;
    font-size: @font-size-sm;

    &.is-error {
      color: @error-color;
    }
  }

  .converted-file-binding {
    display: flex;
    align-items: center;
    gap: @spacing-xs;
    margin-top: @spacing-sm;
    padding: 6px 10px;
    border: 1px solid @accent-color-border;
    border-radius: @border-radius-base;
    background: @accent-color-light;
    color: @text-primary;
    font-size: @font-size-sm;
    flex-wrap: wrap;
  }
</style>
