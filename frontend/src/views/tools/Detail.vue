<template>
  <div class="tool-detail-page">
    <div class="container">
      <a-spin :spinning="loading">
        <div v-if="tool" class="tool-detail-shell">
          <AppPageHeader :title="tool.name" :subtitle="detailSubtitle">
            <template #actions>
              <a-space class="tool-detail-actions" wrap>
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

              <!-- 游客警告 -->
              <a-alert
                v-if="userStore.isGuest"
                type="warning"
                show-icon
                style="margin-bottom: 16px"
              >
                <template #message>
                  {{ t('tools.guestWarning') }}
                </template>
              </a-alert>

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
                <template v-for="(prop, key) in flattenedSchema?.properties" :key="key">
                  <a-form-item
                    :name="key"
                    :label="prop.title"
                    :rules="getFieldRules(key, prop)"
                    :extra="prop.description"
                  >
                    <!-- 文本输入 -->
                    <a-input
                      v-if="prop.type === 'string' && !prop.format && !prop.enum"
                      v-model:value="formState[key]"
                      :placeholder="prop.description"
                    />
                    <!-- 文本域 -->
                    <a-textarea
                      v-else-if="prop.type === 'string' && (prop.format === 'textarea' || prop.format === 'fasta' || prop.format === 'pdb')"
                      v-model:value="formState[key]"
                      :placeholder="prop.description"
                      :rows="prop.format === 'fasta' || prop.format === 'pdb' ? 8 : 4"
                      :class="{ 'code-input': prop.format === 'fasta' || prop.format === 'pdb' }"
                    />
                    <!-- 数字输入 -->
                    <a-input-number
                      v-else-if="prop.type === 'number'"
                      v-model:value="formState[key]"
                      :min="prop.minimum"
                      :max="prop.maximum"
                      style="width: 100%"
                    />
                    <!-- 布尔选择 -->
                    <a-switch
                      v-else-if="prop.type === 'boolean'"
                      v-model:checked="formState[key]"
                    />
                    <!-- 下拉选择 -->
                    <a-select
                      v-else-if="prop.type === 'select' || (prop.enum && prop.type !== 'array')"
                      v-model:value="formState[key]"
                      :placeholder="prop.description"
                    >
                      <a-select-option v-for="opt in prop.enum" :key="opt" :value="opt">
                        {{ opt }}
                      </a-select-option>
                    </a-select>
                    <!-- 数组多选（enum） -->
                    <a-select
                      v-else-if="prop.type === 'array' && prop.items?.enum"
                      v-model:value="formState[key]"
                      mode="multiple"
                      :placeholder="prop.description"
                    >
                      <a-select-option v-for="opt in prop.items.enum" :key="opt" :value="opt">
                        {{ opt }}
                      </a-select-option>
                    </a-select>
                    <!-- 文件上传 / 产物选择 -->
                    <ArtifactFilePicker
                      v-else-if="prop.type === 'file' || prop.format === 'uri' || prop.format === 'file'"
                      :upload-list="fileList[key] ?? []"
                      :selected-artifact="selectedArtifacts[key] ?? null"
                      :accept="prop.accept"
                      :allow-artifacts="userStore.isLoggedIn"
                      :current-tool-id="tool?.id"
                      :current-tool-slug="tool?.slug"
                      @update:upload-list="(files) => handleFileListChange(String(key), files)"
                      @update:selected-artifact="(artifact) => handleArtifactSelection(String(key), artifact)"
                    />
                    <div
                      v-if="isFileSchemaProperty(prop) && exampleFiles[String(key)]"
                      class="example-file-binding"
                    >
                      <FileTextOutlined />
                      <span>{{ t('tools.exampleFileBound') }}: {{ exampleFiles[String(key)]?.filename }}</span>
                      <a-button type="link" size="small" @click="clearExampleFile(String(key))">
                        {{ t('common.clear') }}
                      </a-button>
                    </div>
                  </a-form-item>
                </template>

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
          </div>
        </div>
        </div>
        <a-empty v-else :description="t('common.noData')" />
      </a-spin>
    </div>
    <a-modal
      v-model:open="previewOpen"
      :title="preview?.filename || t('tools.exampleFilePreview')"
      :footer="null"
      width="760px"
    >
      <a-spin :spinning="previewLoading">
        <div v-if="preview" class="example-preview">
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
      </a-spin>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
  import { ref, reactive, computed, onMounted, onBeforeUnmount } from 'vue'
  import { useRoute, useRouter } from 'vue-router'
  import { useI18n } from 'vue-i18n'
  import { message } from 'ant-design-vue'
  import type { FormInstance, Rule } from 'ant-design-vue/es/form'
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
  import ArtifactFilePicker from '@/components/tools/ArtifactFilePicker.vue'
  import ToolExamplePanel from '@/components/tools/ToolExamplePanel.vue'
  import { useToolsStore, useTasksStore, useUserStore } from '@/stores'
  import type {
    ArtifactFile,
    FileUploadResponse,
    SchemaProperty,
    ToolExample,
    ToolExampleFilePreview,
    ToolSchema
  } from '@/types/models'
  import { uploadFile } from '@/api/files'
  import { applyToolExample, getToolExample, previewToolExampleFile } from '@/api/tools'
  import {
    buildTaskSubmissionPayload,
    flattenExampleParams,
    flattenToolInputSchema,
    isFileSchemaProperty,
    type UploadedToolFile
  } from './detail-schema'

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
  const taskName = ref('')
  const formState = reactive<Record<string, unknown>>({})
  const fileList = reactive<Record<string, UploadFile[]>>({})
  const selectedArtifacts = reactive<Record<string, ArtifactFile | undefined>>({})
  const example = ref<ToolExample | null>(null)
  const applyingExample = ref(false)
  const previewOpen = ref(false)
  const previewLoading = ref(false)
  const preview = ref<ToolExampleFilePreview | null>(null)
  const exampleFiles = reactive<Record<string, FileUploadResponse | undefined>>({})

  // 从 current_version.config 中获取 input_schema
  const inputSchema = computed<ToolSchema | undefined>(() => {
    const config = tool.value?.current_version?.config
    if (config && typeof config === 'object' && 'input_schema' in config) {
      return config.input_schema as ToolSchema
    }
    return undefined
  })

  const executorType = computed<string | undefined>(() => {
    const config = tool.value?.current_version?.config
    if (config && typeof config === 'object' && 'type' in config && typeof config.type === 'string') {
      return config.type
    }
    return undefined
  })

  // 扁平化并归一化 schema，隐藏平台内部字段并兼容 input_files / integer / nullable
  const flattenedSchema = computed<ToolSchema | undefined>(() => {
    return flattenToolInputSchema(inputSchema.value)
  })

  const canSubmit = computed(() => {
    if (!userStore.isAuthenticated) return false
    if (userStore.isGuest) return false
    return true
  })
  const detailSubtitle = computed(() => {
    if (!tool.value) {
      return t('tools.detail')
    }

    return `${t('tools.usageCount')}: ${formatNumber(tool.value.statistics?.usage_count)} · ${t('tools.viewCount')}: ${formatNumber(tool.value.statistics?.view_count)}`
  })

  const formatNumber = (num?: number | null) => {
    // 处理 undefined/null 的情况
    if (num == null || num === undefined) {
      return '0'
    }
    if (num >= 10000) {
      return (num / 10000).toFixed(1) + 'w'
    }
    if (num >= 1000) {
      return (num / 1000).toFixed(1) + 'k'
    }
    return num.toString()
  }

  const formatDate = (dateStr: string) => {
    return new Date(dateStr).toLocaleDateString()
  }

  const getStatusColor = (status: string) => {
    const colors: Record<string, string> = {
      draft: 'default',
      published: 'success',
      disabled: 'warning',
      deprecated: 'error'
    }
    return colors[status] || 'default'
  }

  const getFieldRules = (key: string, prop: SchemaProperty): Rule[] => {
    const rules: Rule[] = []
    const schema = flattenedSchema.value
    if (schema?.required?.includes(key)) {
      if (isFileSchemaProperty(prop)) {
        rules.push({
          validator: async () => {
            if (fileList[key]?.length || selectedArtifacts[key] || exampleFiles[key]) {
              return Promise.resolve()
            }
            return Promise.reject(new Error(`${prop.title} ${t('common.required')}`))
          },
          trigger: 'change'
        })
      } else {
        rules.push({ required: true, message: `${prop.title} ${t('common.required')}` })
      }
    }
    if (prop.minLength) {
      rules.push({ min: prop.minLength, message: t('validation.minLength', { min: prop.minLength }) })
    }
    if (prop.maxLength) {
      rules.push({ max: prop.maxLength, message: t('validation.maxLength', { max: prop.maxLength }) })
    }
    return rules
  }

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
    taskName.value = ''
    Object.keys(fileList).forEach(key => {
      fileList[key] = []
    })
    Object.keys(selectedArtifacts).forEach(key => {
      selectedArtifacts[key] = undefined
    })
    Object.keys(exampleFiles).forEach(key => {
      exampleFiles[key] = undefined
    })
  }

  const handleFileListChange = (key: string, files: UploadFile[]) => {
    fileList[key] = files
    if (files.length > 0) {
      selectedArtifacts[key] = undefined
      exampleFiles[key] = undefined
    }
  }

  const handleArtifactSelection = (key: string, artifact: ArtifactFile | null) => {
    selectedArtifacts[key] = artifact ?? undefined
    if (artifact) {
      fileList[key] = []
      exampleFiles[key] = undefined
    }
  }

  const clearExampleFile = (key: string) => {
    exampleFiles[key] = undefined
  }

  const fetchExample = async (toolId: string) => {
    try {
      const res = await getToolExample(toolId)
      example.value = res.data
    } catch {
      example.value = null
    }
  }

  const applyExampleParams = (params: Record<string, unknown>) => {
    const schema = flattenedSchema.value
    if (!schema) {
      return
    }

    const flattenedValues = flattenExampleParams(schema, params)
    Object.entries(flattenedValues).forEach(([key, value]) => {
      formState[key] = value
    })
  }

  const resolveExampleFileFormKey = (field: string): string => {
    const properties = flattenedSchema.value?.properties
    if (!properties) {
      return field
    }

    if (Object.prototype.hasOwnProperty.call(properties, field)) {
      return field
    }

    const nestedMatch = Object.entries(properties).find(([, prop]) => {
      return isFileSchemaProperty(prop) && prop._originalKey === field
    })
    return nestedMatch?.[0] ?? field
  }

  const handleUseExample = async () => {
    if (!tool.value || !example.value) {
      return
    }

    if (!userStore.isLoggedIn) {
      message.warning(t('auth.loginRequired'))
      router.push('/login')
      return
    }

    if (userStore.isGuest) {
      message.warning(t('auth.guestCannotSubmit'))
      return
    }

    applyingExample.value = true
    try {
      const res = await applyToolExample(tool.value.id)
      applyExampleParams(res.data.params)

      Object.entries(res.data.files).forEach(([field, file]) => {
        const formKey = resolveExampleFileFormKey(field)
        exampleFiles[formKey] = file
        fileList[formKey] = []
        selectedArtifacts[formKey] = undefined
      })

      message.success(t('tools.exampleLoaded'))
    } catch {
      // 错误已在请求层处理
    } finally {
      applyingExample.value = false
    }
  }

  const handlePreviewExampleFile = async (field: string) => {
    if (!tool.value) {
      return
    }

    previewOpen.value = true
    previewLoading.value = true
    preview.value = null
    try {
      const res = await previewToolExampleFile(tool.value.id, field)
      preview.value = res.data
    } catch {
      previewOpen.value = false
    } finally {
      previewLoading.value = false
    }
  }

  const handleSubmit = async () => {
    if (!userStore.isLoggedIn) {
      message.warning(t('auth.loginRequired'))
      router.push('/login')
      return
    }

    if (userStore.isGuest) {
      message.warning(t('auth.guestCannotSubmit'))
      return
    }

    submitting.value = true
    try {
      const schema = flattenedSchema.value
      if (!schema) {
        message.error(t('common.noData'))
        return
      }

      const uploadedFiles: Record<string, UploadedToolFile | undefined> = {}
      for (const [key, file] of Object.entries(exampleFiles)) {
        if (!file) {
          continue
        }

        uploadedFiles[key] = {
          fileId: file.id.toString(),
          filename: file.filename,
          downloadUrl: `/api/v1/files/${file.id}/download`
        }
      }

      for (const [key, artifact] of Object.entries(selectedArtifacts)) {
        if (!artifact) {
          continue
        }

        uploadedFiles[key] = {
          fileId: artifact.id,
          filename: artifact.filename,
          downloadUrl: artifact.download_url
        }
      }

      for (const [key, items] of Object.entries(fileList)) {
        const fileItem = items?.[0]
        if (!fileItem?.originFileObj) {
          continue
        }

        const res = await uploadFile(fileItem.originFileObj as File)
        uploadedFiles[key] = {
          fileId: res.data.id.toString(),
          filename: res.data.filename,
          downloadUrl: `/api/v1/files/${res.data.id}/download`
        }
      }

      const payload = buildTaskSubmissionPayload({
        flattenedSchema: schema,
        formState,
        uploadedFiles,
        executorType: executorType.value
      })

      // 创建任务
      const task = await tasksStore.createTask({
        name: taskName.value.trim() || undefined,
        tool_id: tool.value!.id,
        params: payload.params,
        file_ids: payload.fileIds.length > 0 ? payload.fileIds : undefined
      })

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

        // 初始化表单默认值
        if (flattenedSchema.value?.properties) {
          for (const [key, prop] of Object.entries(flattenedSchema.value.properties)) {
            if (prop.default !== undefined) {
              formState[key] = prop.default
            }
            // 初始化文件列表
            if (isFileSchemaProperty(prop)) {
              fileList[key] = []
              selectedArtifacts[key] = undefined
              exampleFiles[key] = undefined
            }
          }
        }
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
    background: @bg-light;
    border: 1px solid #eef0f5;
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
    border: 1px solid #d9f7be;
    border-radius: @border-radius-base;
    background: #fcfff7;
    color: @text-color-light-secondary;
    font-size: @font-size-sm;
    flex-wrap: wrap;
  }

  .example-preview-content {
    max-height: 520px;
    overflow: auto;
    margin: 0;
    padding: @spacing-md;
    border: 1px solid #eef0f5;
    border-radius: @border-radius-base;
    background: #0f172a;
    color: #e5e7eb;
    font-family: monospace;
    font-size: 12px;
    line-height: 1.55;
    white-space: pre-wrap;
    word-break: break-word;
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
