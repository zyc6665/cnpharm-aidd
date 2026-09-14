<template>
  <div class="tool-detail-page">
    <div class="container">
      <SkeletonDetail v-if="loading" />
        <div v-else-if="tool" class="tool-detail-shell">
          <AppPageHeader :title="tool.name" :subtitle="detailSubtitle">
            <template #actions>
              <a-space class="tool-detail-actions" wrap>
                <a-button @click="documentationOpen = true">
                  <InfoCircleOutlined />
                  {{ t('tools.viewIntroduction') }}
                </a-button>
                <a-button
                  :type="tool.is_favorited ? 'primary' : 'default'"
                  :loading="favoriteLoading"
                  @click="handleFavorite"
                >
                  <HeartFilled v-if="tool.is_favorited" />
                  <HeartOutlined v-else />
                  {{ tool.is_favorited ? t('tools.unfavorite') : t('tools.favorite') }}
                </a-button>
                <a-tag v-if="tool.current_version" color="blue">
                  v{{ tool.current_version.version }}
                </a-tag>
              </a-space>
            </template>
          </AppPageHeader>

          <div class="tool-detail">
            <!-- 左侧：工具信息 + 参数表单 -->
            <div class="tool-main">
              <ToolDetailOverview :tool="tool" />

              <!-- 参数表单 -->
              <div class="tool-form card">
                <div class="section-header">
                  <h2 class="section-title">{{ t('tools.parameters') }}</h2>
                </div>

              <ToolExamplePanel
                v-if="example"
                :example="example"
                :applying="applyingExample"
                @preview-file="handlePreviewExampleFile"
                @use-example="handleUseExample"
              />

              <a-form ref="formRef" :model="formState" layout="vertical" @finish="handleSubmit">
                <a-form-item :label="t('tasks.name')">
                  <a-input
                    v-model:value="taskName"
                    :placeholder="t('tasks.namePlaceholder')"
                  />
                </a-form-item>
                <ToolRunInputForm
                  :schema="flattenedSchema"
                  :form-state="formState"
                  :file-list="fileList"
                  :selected-artifacts="selectedArtifacts"
                  :standard-input-slots="standardInputSlots"
                  :show-standard-artifact-inputs="showStandardArtifactInputs"
                  :current-project-id="currentProjectId"
                  :project-artifacts="standardProjectArtifacts"
                  :standard-artifacts-loading="standardArtifactsLoading"
                  :selected-standard-artifacts="selectedStandardArtifacts"
                  :standard-input-file-list="standardInputFileList"
                  :allow-artifacts="userStore.isLoggedIn"
                  :allow-uploads="true"
                  :tool-id="tool?.id"
                  :tool-slug="tool?.slug"
                  :get-file-accept="getFileAccept"
                  :is-file-field-satisfied="isFileFieldSatisfied"
                  :required-message="requiredFieldMessage"
                  :min-length-message="minLengthMessage"
                  :max-length-message="maxLengthMessage"
                  @select-standard-artifact="handleStandardArtifactSelection"
                  @update-standard-upload-list="handleStandardInputFileListChange"
                  @update:file-list="handleFileListChange"
                  @update:selected-artifact="handleArtifactSelection"
                >
                  <template #file-field-extra="{ fieldKey, property }">
                    <ToolFileFieldExtras
                      :field-key="String(fieldKey)"
                      :property="property"
                      :show-sdf-converter="showSdfToPdbConverter(String(fieldKey))"
                      :sdf-conversion-loading="Boolean(sdfConversionLoading[String(fieldKey)])"
                      :sdf-conversion-status-text="sdfConversionStatusText(String(fieldKey))"
                      :sdf-conversion-error="sdfConversionErrors[String(fieldKey)]"
                      :example-file="exampleFiles[String(fieldKey)]"
                      :converted-file="convertedFiles[String(fieldKey)]"
                      :create-sdf-upload-before="createSdfUploadBefore"
                      @clear-example="clearExampleFile"
                      @clear-converted="clearConvertedFile"
                    />
                  </template>
                </ToolRunInputForm>

                <a-form-item class="tool-form-actions">
                  <a-space wrap>
                    <a-button
                      type="primary"
                      html-type="submit"
                      size="large"
                      :loading="submitting"
                      :disabled="!canSubmit"
                    >
                      <PlayCircleOutlined />
                      {{ t('tools.runTool') }}
                    </a-button>
                    <a-button size="large" @click="resetForm">
                      {{ t('common.reset') }}
                    </a-button>
                  </a-space>
                </a-form-item>
              </a-form>
            </div>
          </div>

          <ToolDetailSidebar
            :tool="tool"
            :validation-badges="toolValidationSummary.badges"
            :is-remote-tool-v1="isRemoteToolV1"
            :remote-tool-base-url="remoteToolBaseUrl"
            :remote-tool-manifest-hash="remoteToolManifestHash"
            :remote-tool-smoke-status="remoteToolSmokeStatus"
            :remote-tool-smoke-task-id="remoteToolSmokeTaskId"
            :remote-tool-smoke-error="remoteToolSmokeError"
            :remote-tool-smoke-status-color="remoteToolSmokeStatusColor"
            :remote-tool-smoke-status-text="remoteToolSmokeStatusText"
          />
        </div>
        </div>
        <a-empty v-else :description="t('common.noData')" />
    </div>
    <a-modal
      v-model:open="previewOpen"
      :title="preview?.filename || t('tools.exampleFilePreview')"
      :footer="null"
      width="760px"
    >
      <SkeletonCard v-if="previewLoading" />
        <div v-else-if="preview" class="example-preview">
          <a-alert
            v-if="preview.truncated"
            type="info"
            show-icon
            :message="t('tools.previewTruncated')"
            style="margin-bottom: 12px"
          />
          <pre v-if="preview.previewable" class="example-preview-content">{{ preview.content }}</pre>
          <a-empty v-else :description="t('tools.previewUnavailable')" />
        </div>
    </a-modal>
    <a-modal
      v-model:open="documentationOpen"
      :title="t('tools.introduction')"
      :footer="null"
      width="860px"
      class="tool-documentation-modal"
    >
      <div class="tool-documentation-content" v-html="documentationHtml"></div>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
  import { ref, computed, onMounted, onBeforeUnmount, nextTick } from 'vue'
  import { useRoute, useRouter } from 'vue-router'
  import { useI18n } from 'vue-i18n'
  import { message } from 'ant-design-vue'
  import type { FormInstance } from 'ant-design-vue/es/form'
  import {
    HeartOutlined,
    HeartFilled,
    PlayCircleOutlined,
    InfoCircleOutlined
  } from '@ant-design/icons-vue'
  import AppPageHeader from '@/components/common/AppPageHeader.vue'
  import ToolFileFieldExtras from '@/components/tools/ToolFileFieldExtras.vue'
  import ToolDetailSidebar from '@/components/tools/ToolDetailSidebar.vue'
  import ToolRunInputForm from '@/components/tools/ToolRunInputForm.vue'
  import ToolExamplePanel from '@/components/tools/ToolExamplePanel.vue'
  import SkeletonDetail from '@/components/common/SkeletonDetail.vue'
  import SkeletonCard from '@/components/common/SkeletonCard.vue'
  import { useToolsStore, useTasksStore, useUserStore } from '@/stores'
  import type {
    SchemaProperty,
  } from '@/types/models'
  import { uploadFile, convertSdfToPdb } from '@/api/files'
  import { getProjectArtifacts } from '@/api/artifacts'
  import { applyToolExample, getToolExample, previewToolExampleFile } from '@/api/tools'
  import { useToolDetailExamples } from '@/composables/useToolDetailExamples'
  import {
    useToolDetailPresentation,
    type ToolDetailPresentationLabels,
  } from '@/composables/useToolDetailPresentation'
  import { useToolDetailRunForm } from '@/composables/useToolDetailRunForm'
  import { useToolDetailStandardArtifacts } from '@/composables/useToolDetailStandardArtifacts'
  import { useToolDetailSubmission } from '@/composables/useToolDetailSubmission'
  import {
    getToolFileAccept,
    getToolRequestErrorMessage,
  } from '@/domain/tools'

  const route = useRoute()
  const router = useRouter()
  const { t } = useI18n()
  const toolsStore = useToolsStore()
  const tasksStore = useTasksStore()
  const userStore = useUserStore()

  const formRef = ref<FormInstance>()
  const loading = ref(false)
  const favoriteLoading = ref(false)
  const tool = computed(() => toolsStore.currentTool)
  const documentationOpen = ref(false)

  function clearFieldValidation(key: string) {
    const form = formRef.value as (FormInstance & { clearValidate?: (names?: string[]) => void }) | undefined
    form?.clearValidate?.([key])
  }

  async function revalidateField(key: string) {
    await nextTick()
    await formRef.value?.validateFields([key]).catch(() => undefined)
  }

  const {
    taskName,
    formState,
    fileList,
    selectedArtifacts,
    selectedStandardArtifacts,
    standardInputFileList,
    exampleFiles,
    convertedFiles,
    sdfConversionLoading,
    sdfConversionErrors,
    flattenedSchema,
    standardInputSlots,
    standardInputFileFieldBindings,
    showStandardArtifactInputs,
    missingRequiredStandardSlots,
    canSubmit,
    initializeFromSurface,
    reset: resetRunForm,
    selectStandardArtifact,
    updateStandardInputFileList,
    handleFileListChange,
    handleArtifactSelection,
    isFileFieldSatisfied,
    clearExampleFile: clearExampleFileState,
    clearConvertedFile,
    showSdfToPdbConverter,
    sdfConversionStatusText,
    createSdfUploadBefore,
  } = useToolDetailRunForm({
    tool,
    isAuthenticated: computed(() => userStore.isAuthenticated),
    sdfConversion: {
      convert: async file => (await convertSdfToPdb(file)).data,
      getErrorMessage: getToolRequestErrorMessage,
      clearFieldValidation,
      revalidateField,
      onInvalidFile: () => message.warning('请上传 SDF 文件'),
      onSuccess: () => message.success('SDF 已转换为 PDB'),
    },
  })

  const {
    example,
    applyingExample,
    previewOpen,
    previewLoading,
    preview,
    fetchExample,
    handleUseExample,
    handlePreviewExampleFile,
  } = useToolDetailExamples({
    tool,
    isLoggedIn: computed(() => userStore.isLoggedIn),
    flattenedSchema,
    formState,
    fileList,
    selectedArtifacts,
    exampleFiles,
    convertedFiles,
    api: {
      getExample: getToolExample,
      applyExample: applyToolExample,
      previewFile: previewToolExampleFile,
    },
    onRequireLogin: () => {
      message.warning(t('auth.loginRequired'))
      router.push('/login')
    },
    onExampleLoaded: () => message.success(t('tools.exampleLoaded')),
  })

  const presentationLabels = computed<ToolDetailPresentationLabels>(() => ({
    detailFallback: t('tools.detail'),
    usageCount: t('tools.usageCount'),
    viewCount: t('tools.viewCount'),
    title: t('tools.introduction'),
    overview: t('tools.modelOverview'),
    parameters: t('tools.parameterDocs'),
    outputs: t('tools.outputDocs'),
    outputPatterns: t('tools.outputPatterns'),
    name: t('common.name'),
    required: t('common.required'),
    optional: t('common.optional'),
    defaultValue: t('tools.defaultValue'),
    type: t('tools.fieldType'),
    description: t('common.description'),
    range: t('tools.valueRange'),
    noDocumentation: t('tools.noDocumentation'),
  }))

  const {
    toolValidationSummary,
    executorType,
    isRemoteToolV1,
    remoteToolBaseUrl,
    remoteToolManifestHash,
    remoteToolSmokeStatus,
    remoteToolSmokeTaskId,
    remoteToolSmokeError,
    remoteToolSmokeStatusColor,
    remoteToolSmokeStatusText,
    detailSubtitle,
    documentationHtml,
  } = useToolDetailPresentation({
    tool,
    inputSchema: flattenedSchema,
    labels: presentationLabels,
  })

  const currentProjectId = computed(() => {
    const raw = route.query.project_id ?? route.query.projectId ?? route.params.projectId
    const value = Array.isArray(raw) ? raw[0] : raw
    return typeof value === 'string' && value.trim() ? value.trim() : undefined
  })

  const {
    standardProjectArtifacts,
    standardArtifactsLoading,
    loadStandardProjectArtifacts,
    handleStandardArtifactSelection,
    handleStandardInputFileListChange,
  } = useToolDetailStandardArtifacts({
    projectId: currentProjectId,
    standardInputSlots,
    api: { getProjectArtifacts },
    selectStandardArtifact,
    updateStandardInputFileList,
  })

  const { submitting, handleSubmit } = useToolDetailSubmission({
    isLoggedIn: computed(() => userStore.isLoggedIn),
    toolId: computed(() => tool.value?.id),
    taskName,
    projectId: currentProjectId,
    flattenedSchema,
    formState,
    fileList,
    selectedArtifacts,
    resolvedFiles: {
      example: exampleFiles,
      converted: convertedFiles,
    },
    standardInputSlots,
    standardInputFileFieldBindings,
    selectedStandardArtifacts,
    standardInputFileList,
    executorType,
    missingRequiredStandardSlots,
    api: {
      uploadFile: async file => (await uploadFile(file)).data,
      prepareTaskRun: payload => tasksStore.prepareTaskRun(payload),
      createTask: payload => tasksStore.createTask(payload),
    },
    onRequireLogin: () => {
      message.warning(t('auth.loginRequired'))
      router.push('/login')
    },
    onNoSchema: () => message.error(t('common.noData')),
    onMissingStandardInputs: slotNames => {
      message.error(`请选择或上传标准 Artifact 输入：${slotNames.join(', ')}`)
    },
    onBlocked: blockedMessage => message.error(blockedMessage),
    onTaskCreated: task => {
      message.success(t('tasks.created'))
      router.push(`/tasks/${task.id}`)
    },
  })

  const requiredFieldMessage = (title: string) => `${title} ${t('common.required')}`
  const minLengthMessage = (min: number) => t('validation.minLength', { min })
  const maxLengthMessage = (max: number) => t('validation.maxLength', { max })

  const handleFavorite = async () => {
    if (!userStore.isLoggedIn) {
      message.warning(t('auth.loginRequired'))
      router.push('/login')
      return
    }
    favoriteLoading.value = true
    try {
      await toolsStore.toggleFavorite(tool.value!.id)
    } finally {
      favoriteLoading.value = false
    }
  }

  const resetForm = () => {
    formRef.value?.resetFields()
    resetRunForm()
  }

  const getFileAccept = (key: string, prop: SchemaProperty): string | undefined => {
    return getToolFileAccept({ key, property: prop, toolSlug: tool.value?.slug })
  }

  const clearExampleFile = (key: string) => {
    clearExampleFileState(key)
  }

  onMounted(async () => {
    const id = route.params.id as string
    if (id) {
      loading.value = true
      try {
        await toolsStore.fetchToolDetail(id)

        initializeFromSurface()
        await loadStandardProjectArtifacts()
        await fetchExample(id)
      } finally {
        loading.value = false
      }
    }
  })

  onBeforeUnmount(() => {
    toolsStore.clearCurrentTool()
  })
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .tool-detail-page {
    padding: @spacing-xl 0;
    min-height: calc(100vh - @header-height - @footer-height);
  }

  .tool-detail-actions {
    align-items: center;
    justify-content: flex-end;
  }

  .tool-detail {
    display: grid;
    grid-template-columns: 1fr 320px;
    gap: @spacing-xl;

    @media (max-width: @screen-lg) {
      grid-template-columns: 1fr;
    }
  }

  .card {
    background: @bg-elevated;
    border: 1px solid @border-color;
    border-radius: @border-radius-lg;
    padding: @spacing-lg;
    box-shadow: @shadow-sm;
  }

  .tool-main {
    display: flex;
    flex-direction: column;
    gap: @spacing-xl;
  }

  .tool-form {
    .section-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: @spacing-md;
      margin-bottom: @spacing-lg;
      flex-wrap: wrap;
    }

    .section-title {
      font-size: @font-size-lg;
      font-weight: @font-weight-semibold;
      margin-bottom: 0;
    }

    .code-input {
      font-family: monospace;
    }

    .file-item {
      display: flex;
      align-items: center;
      gap: @spacing-xs;
    }

    .tool-form-actions {
      margin-bottom: 0;
    }
  }

  .example-preview-content {
    max-height: 520px;
    overflow: auto;
    margin: 0;
    padding: @spacing-md;
    border: 1px solid @border-color;
    border-radius: @border-radius-base;
    background: #0f172a;
    color: #e5e7eb;
    font-family: monospace;
    font-size: 12px;
    line-height: 1.55;
    white-space: pre-wrap;
    word-break: break-word;
  }

  .tool-documentation-content {
    max-height: 68vh;
    overflow: auto;
    color: @text-color-light-secondary;
    line-height: @line-height-loose;

    :deep(h1),
    :deep(h2),
    :deep(h3) {
      color: @text-color-light-primary;
      font-weight: @font-weight-semibold;
      margin: @spacing-lg 0 @spacing-sm;
    }

    :deep(h1) {
      margin-top: 0;
      font-size: 24px;
    }

    :deep(h2) {
      font-size: @font-size-lg;
    }

    :deep(h3) {
      font-size: @font-size-md;
    }

    :deep(p),
    :deep(ul),
    :deep(table),
    :deep(pre) {
      margin-bottom: @spacing-md;
    }

    :deep(ul) {
      padding-left: @spacing-xl;
    }

    :deep(table) {
      width: 100%;
      border-collapse: collapse;
      font-size: @font-size-sm;
    }

    :deep(th),
    :deep(td) {
      padding: 8px 10px;
      border: 1px solid @border-color;
      vertical-align: top;
    }

    :deep(th) {
      background: @bg-hover;
      color: @text-primary;
      font-weight: @font-weight-semibold;
    }

    :deep(code) {
      padding: 2px 5px;
      border-radius: 4px;
      background: @bg-hover;
      color: @text-secondary;
      font-family: monospace;
      font-size: 12px;
    }

    :deep(pre) {
      padding: @spacing-md;
      border-radius: @border-radius-base;
      background: @bg-body;
      border: 1px solid @border-color;
      overflow: auto;

      code {
        padding: 0;
        background: transparent;
        color: @text-primary;
      }
    }

    :deep(a) {
      color: @accent-color;
    }
  }

  :deep(.ant-btn-primary) {
    background: @accent-color;
    border-color: @accent-color;

    &:hover {
      background: @accent-color-hover;
      border-color: @accent-color-hover;
    }
  }

  @media (max-width: @screen-md) {
    .tool-detail-page {
      padding: @spacing-lg 0;
    }

    .tool-detail-actions {
      justify-content: flex-start;
      width: 100%;
    }

    .card {
      padding: @spacing-md;
    }

    .tool-form-actions {
      :deep(.ant-space) {
        width: 100%;
      }

      :deep(.ant-btn) {
        width: 100%;
      }
    }

    .tool-form .section-header {
      align-items: stretch;

      :deep(.ant-btn) {
        width: 100%;
      }
    }
  }
</style>
