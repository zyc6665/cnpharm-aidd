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
              <!-- 工具信息卡片 -->
              <div class="tool-info tool-overview card">
              <div class="tool-header">
                <div class="tool-icon">
                  <span v-if="tool.icon">{{ tool.icon }}</span>
                  <ToolOutlined v-else />
                </div>
                <div class="tool-meta">
                  <h2 class="overview-title">{{ t('tools.toolInfo') }}</h2>
                  <div class="tool-tags">
                    <a-tag v-if="tool.category" color="gold">{{ tool.category }}</a-tag>
                    <a-tag v-for="tag in tool.tags" :key="tag.id" :color="tag.color">
                      {{ tag.name }}
                    </a-tag>
                  </div>
                </div>
              </div>

              <p class="tool-description">{{ tool.description }}</p>

              <div class="tool-stats">
                <span class="stat-item">
                  <PlayCircleOutlined />
                  {{ t('tools.usageCount') }}: {{ formatNumber(tool.statistics?.usage_count) }}
                </span>
                <span class="stat-item">
                  <EyeOutlined />
                  {{ t('tools.viewCount') }}: {{ formatNumber(tool.statistics?.view_count) }}
                </span>
                <span class="stat-item">
                  <HeartOutlined />
                  {{ t('tools.favoriteCount') }}: {{ formatNumber(tool.statistics?.favorite_count) }}
                </span>
                <span v-if="tool.current_version" class="stat-item">
                  <TagOutlined />
                  {{ t('tools.version') }}: v{{ tool.current_version.version }}
                </span>
              </div>

              <!-- 版本更新日志 -->
              <div v-if="tool.current_version?.changelog" class="tool-changelog">
                <h3>{{ t('tools.changelog') }}</h3>
                <p>{{ tool.current_version.changelog }}</p>
              </div>
            </div>

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
                    <div
                      v-if="showSdfToPdbConverter(String(fieldKey))"
                      class="sdf-converter"
                    >
                      <div class="sdf-converter__copy">
                        <strong>SDF 转 Ligand PDB</strong>
                        <span>上传一个 SDF 文件，转换后自动填入 ligand_pdb。</span>
                      </div>
                      <a-upload
                        accept=".sdf"
                        :show-upload-list="false"
                        :before-upload="createSdfUploadBefore(String(fieldKey))"
                      >
                        <a-button size="small" :loading="sdfConversionLoading[String(fieldKey)]">
                          <FileTextOutlined />
                          上传 SDF 并转换
                        </a-button>
                      </a-upload>
                    </div>
                    <div
                      v-if="showSdfToPdbConverter(String(fieldKey)) && sdfConversionStatusText(String(fieldKey))"
                      class="sdf-converter-status"
                      :class="{ 'is-error': Boolean(sdfConversionErrors[String(fieldKey)]) }"
                    >
                      {{ sdfConversionStatusText(String(fieldKey)) }}
                    </div>
                    <div
                      v-if="isFileSchemaProperty(property) && exampleFiles[String(fieldKey)]"
                      class="example-file-binding"
                    >
                      <FileTextOutlined />
                      <span>{{ t('tools.exampleFileBound') }}: {{ exampleFiles[String(fieldKey)]?.filename }}</span>
                      <a-button type="link" size="small" @click="clearExampleFile(String(fieldKey))">
                        {{ t('common.clear') }}
                      </a-button>
                    </div>
                    <div
                      v-if="isFileSchemaProperty(property) && convertedFiles[String(fieldKey)]"
                      class="converted-file-binding"
                    >
                      <FileTextOutlined />
                      <span>已转换: {{ convertedFiles[String(fieldKey)]?.filename }}</span>
                      <a-button type="link" size="small" @click="clearConvertedFile(String(fieldKey))">
                        {{ t('common.clear') }}
                      </a-button>
                    </div>
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

          <!-- 右侧：工具信息 -->
          <div class="tool-sidebar">
            <!-- 工具标签 -->
            <div v-if="tool.tags?.length" class="tags-info card">
              <h3 class="sidebar-title">
                <TagOutlined />
                {{ t('tools.tags') }}
              </h3>
              <div class="tags-list">
                <a-tag v-for="tag in tool.tags" :key="tag.id" :color="tag.color">
                  {{ tag.name }}
                </a-tag>
              </div>
            </div>

            <!-- 工具状态 -->
            <div class="status-info card">
              <h3 class="sidebar-title">
                <InfoCircleOutlined />
                {{ t('tools.toolInfo') }}
              </h3>
              <div class="info-list">
                <div class="info-item">
                  <span class="info-label">{{ t('tools.status') }}:</span>
                  <a-tag :color="getStatusColor(tool.status)">{{ tool.status }}</a-tag>
                </div>
                <div class="info-item validation-info">
                  <span class="info-label">验证等级:</span>
                  <a-space size="small" wrap>
                    <a-tag
                      v-for="badge in toolValidationSummary.badges"
                      :key="badge.label"
                      :color="badge.color"
                    >
                      {{ badge.label }}
                    </a-tag>
                  </a-space>
                </div>
                <div class="info-item">
                  <span class="info-label">{{ t('common.createdAt') }}:</span>
                  <span>{{ formatDate(tool.created_at) }}</span>
                </div>
                <div v-if="tool.updated_at" class="info-item">
                  <span class="info-label">{{ t('common.updatedAt') }}:</span>
                  <span>{{ formatDate(tool.updated_at) }}</span>
                </div>
              </div>
            </div>

            <div v-if="isRemoteToolV1" class="remote-tool-info card">
              <h3 class="sidebar-title">
                <InfoCircleOutlined />
                远程 API
              </h3>
              <div class="remote-tool-info-list">
                <div class="remote-tool-info-item">
                  <span class="remote-tool-info-label">协议:</span>
                  <a-tag color="blue">remote_tool_v1</a-tag>
                </div>
                <div v-if="remoteToolBaseUrl" class="remote-tool-info-item">
                  <span class="remote-tool-info-label">服务:</span>
                  <span class="remote-tool-info-value">{{ remoteToolBaseUrl }}</span>
                </div>
                <div v-if="remoteToolManifestHash" class="remote-tool-info-item">
                  <span class="remote-tool-info-label">manifest_sha256:</span>
                  <code class="remote-tool-manifest-hash">{{ remoteToolManifestHash }}</code>
                </div>
                <div class="remote-tool-info-item">
                  <span class="remote-tool-info-label">smoke test:</span>
                  <a-tag :color="remoteToolSmokeStatusColor(remoteToolSmokeStatus)">
                    {{ remoteToolSmokeStatusText(remoteToolSmokeStatus) }}
                  </a-tag>
                </div>
                <div v-if="remoteToolSmokeTaskId" class="remote-tool-info-item">
                  <span class="remote-tool-info-label">任务:</span>
                  <router-link :to="`/tasks/${remoteToolSmokeTaskId}`">
                    查看 smoke test 任务
                  </router-link>
                </div>
                <div v-if="remoteToolSmokeError" class="remote-tool-info-item">
                  <span class="remote-tool-info-label">失败原因:</span>
                  <span class="remote-tool-info-value">{{ remoteToolSmokeError }}</span>
                </div>
              </div>
            </div>
          </div>
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
  import type { UploadFile } from 'ant-design-vue'
  import {
    ToolOutlined,
    HeartOutlined,
    HeartFilled,
    PlayCircleOutlined,
    EyeOutlined,
    TagOutlined,
    InfoCircleOutlined,
    FileTextOutlined
  } from '@ant-design/icons-vue'
  import AppPageHeader from '@/components/common/AppPageHeader.vue'
  import ToolRunInputForm from '@/components/tools/ToolRunInputForm.vue'
  import ToolExamplePanel from '@/components/tools/ToolExamplePanel.vue'
  import SkeletonDetail from '@/components/common/SkeletonDetail.vue'
  import SkeletonCard from '@/components/common/SkeletonCard.vue'
  import { useToolsStore, useTasksStore, useUserStore } from '@/stores'
  import type {
    SchemaProperty,
  } from '@/types/models'
  import type { TypedArtifact } from '@/types/artifacts'
  import { uploadFile, convertSdfToPdb } from '@/api/files'
  import { getProjectArtifacts } from '@/api/artifacts'
  import { applyToolExample, getToolExample, previewToolExampleFile } from '@/api/tools'
  import { useToolDetailExamples } from '@/composables/useToolDetailExamples'
  import {
    useToolDetailPresentation,
    type ToolDetailPresentationLabels,
  } from '@/composables/useToolDetailPresentation'
  import { useToolDetailRunForm } from '@/composables/useToolDetailRunForm'
  import {
    buildToolRunTaskPayload,
    formatToolDate as formatDate,
    formatToolMetricCount as formatNumber,
    getToolFileAccept,
    getToolRequestErrorMessage,
    getToolStatusColor as getStatusColor,
    isFileSchemaProperty,
  } from '@/domain/tools'
  import { taskRunPreparationBlockedMessage } from '@/domain/tasks'

  const route = useRoute()
  const router = useRouter()
  const { t } = useI18n()
  const toolsStore = useToolsStore()
  const tasksStore = useTasksStore()
  const userStore = useUserStore()

  const formRef = ref<FormInstance>()
  const loading = ref(false)
  const submitting = ref(false)
  const favoriteLoading = ref(false)
  const tool = computed(() => toolsStore.currentTool)
  const standardProjectArtifacts = ref<TypedArtifact[]>([])
  const standardArtifactsLoading = ref(false)
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

  const loadStandardProjectArtifacts = async () => {
    if (!currentProjectId.value || !standardInputSlots.value.length) {
      standardProjectArtifacts.value = []
      return
    }

    standardArtifactsLoading.value = true
    try {
      const res = await getProjectArtifacts(currentProjectId.value)
      standardProjectArtifacts.value = res.data.items
    } catch {
      standardProjectArtifacts.value = []
    } finally {
      standardArtifactsLoading.value = false
    }
  }

  const handleStandardArtifactSelection = (slotName: string, versionId?: string) => {
    selectStandardArtifact(slotName, versionId, standardProjectArtifacts.value)
  }

  const handleStandardInputFileListChange = (slotName: string, files: UploadFile[]) => {
    updateStandardInputFileList(slotName, files)
  }

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

  const handleSubmit = async () => {
    if (!userStore.isLoggedIn) {
      message.warning(t('auth.loginRequired'))
      router.push('/login')
      return
    }

    submitting.value = true
    try {
      const schema = flattenedSchema.value
      if (!schema) {
        message.error(t('common.noData'))
        return
      }
      if (missingRequiredStandardSlots.value.length) {
        message.error(`请选择或上传标准 Artifact 输入：${missingRequiredStandardSlots.value.map(slot => slot.name).join(', ')}`)
        return
      }

      const taskPayload = await buildToolRunTaskPayload({
        toolId: tool.value!.id,
        taskName: taskName.value,
        projectId: currentProjectId.value,
        flattenedSchema: schema,
        formState,
        fileList,
        selectedArtifacts,
        resolvedFiles: {
          example: exampleFiles,
          converted: convertedFiles,
        },
        standardInputSlots: standardInputSlots.value,
        standardInputFileFieldBindings: standardInputFileFieldBindings.value,
        selectedStandardArtifacts,
        standardInputFileList,
        executorType: executorType.value,
        uploadFile: async file => (await uploadFile(file)).data,
      })

      const preparationPreview = await tasksStore.prepareTaskRun(taskPayload)
      const blockedMessage = taskRunPreparationBlockedMessage(preparationPreview)
      if (blockedMessage) {
        message.error(blockedMessage)
        return
      }

      // 创建任务
      const task = await tasksStore.createTask(taskPayload)

      message.success(t('tasks.created'))
      router.push(`/tasks/${task.id}`)
    } catch {
      // 错误已在请求层处理
    } finally {
      submitting.value = false
    }
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

  .tool-info {
    .tool-header {
      display: flex;
      gap: @spacing-md;
      margin-bottom: @spacing-lg;
      flex-wrap: wrap;
    }

    .tool-icon {
      width: 64px;
      height: 64px;
      border-radius: @border-radius-lg;
      background: @accent-color-light;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 32px;
      color: @accent-color;
      flex-shrink: 0;
    }

    .tool-meta {
      flex: 1;
      min-width: 200px;
    }

    .overview-title {
      font-size: @font-size-lg;
      font-weight: @font-weight-semibold;
      margin-bottom: @spacing-sm;
    }

    .tool-tags {
      display: flex;
      gap: @spacing-xs;
      flex-wrap: wrap;
    }

    .tool-description {
      color: @text-color-light-secondary;
      font-size: @font-size-md;
      margin-bottom: @spacing-lg;
      line-height: @line-height-loose;
    }

    .tool-stats {
      display: flex;
      gap: @spacing-lg;
      flex-wrap: wrap;
      margin-bottom: @spacing-lg;
    }

    .stat-item {
      display: flex;
      align-items: center;
      gap: @spacing-xs;
      color: @text-color-light-tertiary;
    }

    .tool-changelog {
      margin-top: @spacing-lg;
      padding-top: @spacing-lg;
      border-top: 1px solid @border-color-light;

      h3 {
        font-size: @font-size-md;
        font-weight: @font-weight-semibold;
        margin-bottom: @spacing-sm;
      }

      p {
        color: @text-color-light-secondary;
        font-size: @font-size-sm;
      }
    }
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

  // 右侧栏
  .tool-sidebar {
    display: flex;
    flex-direction: column;
    gap: @spacing-lg;

    @media (min-width: @screen-lg) {
      position: sticky;
      top: @spacing-lg;
      align-self: start;
    }

    @media (max-width: @screen-lg) {
      order: -1;
    }
  }

  .sidebar-title {
    font-size: @font-size-md;
    font-weight: @font-weight-semibold;
    margin-bottom: @spacing-md;
    display: flex;
    align-items: center;
    gap: @spacing-xs;
  }

  .tags-info {
    .tags-list {
      display: flex;
      flex-wrap: wrap;
      gap: @spacing-xs;
    }
  }

  .status-info {
    .info-list {
      display: flex;
      flex-direction: column;
      gap: @spacing-sm;
    }

    .info-item {
      display: flex;
      align-items: center;
      gap: @spacing-sm;
      font-size: @font-size-sm;
    }

    .info-label {
      color: @text-color-light-tertiary;
      min-width: 70px;
    }
  }

  .remote-tool-info-list {
    display: flex;
    flex-direction: column;
    gap: @spacing-sm;
  }

  .remote-tool-info-item {
    display: flex;
    align-items: flex-start;
    gap: @spacing-sm;
    font-size: @font-size-sm;
  }

  .remote-tool-info-label {
    min-width: 96px;
    color: @text-color-light-tertiary;
  }

  .remote-tool-info-value,
  .remote-tool-manifest-hash {
    flex: 1;
    min-width: 0;
    word-break: break-all;
  }

  .remote-tool-manifest-hash {
    color: @text-color-light-secondary;
    font-family: monospace;
    font-size: 12px;
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

    .tool-info .tool-header {
      align-items: flex-start;
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
