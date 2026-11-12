<template>
  <div class="tool-detail-page">
    <div class="container">
      <SkeletonDetail v-if="loading && !tool" />
      <div v-else-if="tool" class="tool-detail-shell">
        <AppPageHeader :title="tool.name" :subtitle="detailSubtitle">
          <template #actions>
            <ToolDetailHeaderActions
              :tool="tool"
              :favorite-loading="favoriteLoading"
              @view-documentation="documentationOpen = true"
              @toggle-favorite="handleFavorite"
            />
          </template>
        </AppPageHeader>

        <div class="tool-detail">
          <div class="tool-main">
            <ToolDetailOverview :tool="tool" />

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
                  :project-artifact-placeholder="t('tools.selectProjectArtifact')"
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

                <ToolRunFormActions
                  :submitting="submitting"
                  :can-submit="canSubmit"
                  :disabled-reason="userStore.isAuthenticated ? undefined : t('auth.loginRequired')"
                  :login-required="!userStore.isAuthenticated"
                  @login="handleLogin"
                  @reset="resetForm"
                />
              </a-form>
            </div>
          </div>

        </div>
      </div>
      <!-- 工具不可用不是「暂无数据」：要么已被下架，要么当前账号无权访问，
           两种都需要说清楚，否则用户会以为是自己点错了。 -->
      <AppEmptyState
        v-else
        :title="t('common.noData')"
        :description="t('tools.detailUnavailableHint')"
      />
    </div>
    <ToolDetailModals
      v-model:preview-open="previewOpen"
      v-model:documentation-open="documentationOpen"
      :preview-loading="previewLoading"
      :preview="preview"
      :documentation-html="documentationHtml"
    />
  </div>
</template>

<script setup lang="ts">
  import { ref, computed, watch, onBeforeUnmount, nextTick } from 'vue'
  import { useRoute, useRouter } from 'vue-router'
  import { useI18n } from 'vue-i18n'
  import { message } from 'ant-design-vue'
  import type { FormInstance } from 'ant-design-vue/es/form'
  import AppPageHeader from '@/components/common/AppPageHeader.vue'
  import AppEmptyState from '@/components/common/AppEmptyState.vue'
  import ToolDetailOverview from '@/components/tools/ToolDetailOverview.vue'
  import ToolDetailHeaderActions from '@/components/tools/ToolDetailHeaderActions.vue'
  import ToolFileFieldExtras from '@/components/tools/ToolFileFieldExtras.vue'
  import ToolDetailModals from '@/components/tools/ToolDetailModals.vue'
  import ToolRunInputForm from '@/components/tools/ToolRunInputForm.vue'
  import ToolRunFormActions from '@/components/tools/ToolRunFormActions.vue'
  import ToolExamplePanel from '@/components/tools/ToolExamplePanel.vue'
  import SkeletonDetail from '@/components/common/SkeletonDetail.vue'
  import { useToolsStore, useTasksStore, useUserStore } from '@/stores'
  import type {
    SchemaProperty,
  } from '@/types/models'
  import { uploadFile, convertSdfToPdb } from '@/api/files'
  import { getAllProjectArtifacts } from '@/api/artifacts'
  import { applyToolExample, getToolExample, previewToolExampleFile } from '@/api/tools'
  import { useToolDetailExamples } from '@/composables/useToolDetailExamples'
  import {
    useToolDetailPresentation,
    type ToolDetailPresentationLabels,
  } from '@/composables/useToolDetailPresentation'
  import { useToolDetailRunForm } from '@/composables/useToolDetailRunForm'
  import { useToolDetailStandardArtifacts } from '@/composables/useToolDetailStandardArtifacts'
  import { useToolDetailSubmission } from '@/composables/useToolDetailSubmission'
  import { getToolFileAccept, getToolRequestErrorMessage } from '@/domain/tools'

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
    executorType,
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
    api: { getAllProjectArtifacts },
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
    onMissingStandardInputs: slotNames => message.error(
      t('tasks.missingInputs', { inputs: slotNames.join(', ') })
    ),
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

  const handleLogin = () => {
    router.push({ name: 'Login', query: { redirect: route.fullPath } })
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

  let detailLoadId = 0
  watch(
    () => route.params.id,
    async rawId => {
      const id = Array.isArray(rawId) ? rawId[0] : rawId
      const requestId = ++detailLoadId
      if (typeof id !== 'string' || !id.trim()) {
        toolsStore.clearCurrentTool()
        return
      }

      loading.value = true
      toolsStore.clearCurrentTool()
      resetRunForm()
      example.value = null
      try {
        await toolsStore.fetchToolDetail(id)
        if (requestId !== detailLoadId || String(route.params.id) !== id) {
          return
        }

        initializeFromSurface()
        await Promise.allSettled([loadStandardProjectArtifacts(), fetchExample(id)])
      } finally {
        if (requestId === detailLoadId) {
          loading.value = false
        }
      }
    },
    { immediate: true }
  )

  watch(currentProjectId, () => {
    if (tool.value) {
      void loadStandardProjectArtifacts()
    }
  })

  onBeforeUnmount(() => {
    detailLoadId += 1
    toolsStore.clearCurrentTool()
  })
</script>

<style scoped lang="less">
  @import '@/assets/styles/variables.less';

  .tool-detail-page {
    padding: @spacing-xl 0;
    min-height: calc(100vh - @header-height - @footer-height);
  }

  .tool-detail {
    display: flex;
    justify-content: center;
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
    width: 100%;
    max-width: @page-max-width;
    min-width: 0;
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

    .card {
      padding: @spacing-md;
    }

    .tool-form .section-header {
      align-items: stretch;

      :deep(.ant-btn) {
        width: 100%;
      }
    }
  }
</style>
