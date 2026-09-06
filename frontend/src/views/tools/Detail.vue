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
                <div v-if="standardInputSlots.length" class="standard-artifact-inputs">
                  <div class="standard-artifact-inputs__header">
                    <span>标准 Artifact 输入</span>
                    <a-tag color="blue">Tool Package v2</a-tag>
                  </div>
                  <a-alert
                    v-if="!currentProjectId"
                    type="warning"
                    show-icon
                    message="标准 Artifact 输入需要项目上下文，请从项目内进入工具或在 URL 带 project_id。"
                  />
                  <a-alert
                    v-else-if="!standardArtifactsLoading && standardProjectArtifacts.length === 0"
                    type="info"
                    show-icon
                    message="当前项目暂无可绑定的标准 Artifact。"
                  />
                  <a-form-item
                    v-for="slot in standardInputSlots"
                    :key="slot.name"
                    :label="slot.name"
                    :required="slot.required"
                    :extra="`标准类型：${slot.type}`"
                  >
                    <a-select
                      :value="selectedStandardArtifacts[slot.name]?.latest_version.id"
                      :disabled="!currentProjectId"
                      :loading="standardArtifactsLoading"
                      allow-clear
                      show-search
                      option-filter-prop="label"
                      placeholder="选择项目中的兼容 ArtifactVersion"
                      @change="handleStandardArtifactSelection(slot.name, $event)"
                    >
                      <a-select-option
                        v-for="artifact in compatibleStandardArtifacts(slot)"
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
                  </a-form-item>
                </div>
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
                      :accept="getFileAccept(String(key), prop)"
                      :allow-artifacts="userStore.isLoggedIn"
                      :current-tool-id="tool?.id"
                      :current-tool-slug="tool?.slug"
                      @update:upload-list="(files) => handleFileListChange(String(key), files)"
                      @update:selected-artifact="(artifact) => handleArtifactSelection(String(key), artifact)"
                    />
                    <div
                      v-if="showSdfToPdbConverter(String(key))"
                      class="sdf-converter"
                    >
                      <div class="sdf-converter__copy">
                        <strong>SDF 转 Ligand PDB</strong>
                        <span>上传一个 SDF 文件，转换后自动填入 ligand_pdb。</span>
                      </div>
                      <a-upload
                        accept=".sdf"
                        :show-upload-list="false"
                        :before-upload="createSdfUploadBefore(String(key))"
                      >
                        <a-button size="small" :loading="sdfConversionLoading[String(key)]">
                          <FileTextOutlined />
                          上传 SDF 并转换
                        </a-button>
                      </a-upload>
                    </div>
                    <div
                      v-if="showSdfToPdbConverter(String(key)) && sdfConversionStatusText(String(key))"
                      class="sdf-converter-status"
                      :class="{ 'is-error': Boolean(sdfConversionErrors[String(key)]) }"
                    >
                      {{ sdfConversionStatusText(String(key)) }}
                    </div>
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
                    <div
                      v-if="isFileSchemaProperty(prop) && convertedFiles[String(key)]"
                      class="converted-file-binding"
                    >
                      <FileTextOutlined />
                      <span>已转换: {{ convertedFiles[String(key)]?.filename }}</span>
                      <a-button type="link" size="small" @click="clearConvertedFile(String(key))">
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
  import { ref, reactive, computed, onMounted, onBeforeUnmount, nextTick } from 'vue'
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
  import SkeletonDetail from '@/components/common/SkeletonDetail.vue'
  import SkeletonCard from '@/components/common/SkeletonCard.vue'
  import { useToolsStore, useTasksStore, useUserStore } from '@/stores'
  import type {
    ArtifactFile,
    FileUploadResponse,
    SchemaProperty,
    ToolExample,
    ToolExampleFilePreview,
    ToolSchema
  } from '@/types/models'
  import type { TypedArtifact } from '@/types/artifacts'
  import { uploadFile, convertSdfToPdb } from '@/api/files'
  import { getProjectArtifacts } from '@/api/artifacts'
  import { applyToolExample, getToolExample, previewToolExampleFile } from '@/api/tools'
  import { getToolValidationSummary } from '@/utils/tool-validation'
  import {
    buildTaskSubmissionPayload,
    formatToolDate as formatDate,
    formatToolMetricCount as formatNumber,
    flattenExampleParams,
    flattenToolInputSchema,
    getSdfConversionStatusText,
    getToolFileAccept,
    getToolRequestErrorMessage,
    getToolStatusColor as getStatusColor,
    isFileSchemaProperty,
    resolveExampleFileFormKey,
    type UploadedToolFile
  } from '@/domain/tools'
  import { taskRunPreparationBlockedMessage } from '@/domain/tasks'
  import {
    buildFallbackToolDocumentation,
    renderMarkdownToHtml,
    type ToolDocumentationLabels
  } from '@/domain/tools'
  import {
    buildStandardInputBindings,
    buildStandardRunTaskExtras,
    filterCompatibleProjectArtifacts,
    formatStandardArtifactLabel,
    resolveToolPackageParameterSchema,
    resolveToolStandardInputSlots,
    shouldShowSdfToPdbConverter,
    type StandardArtifactInputSlot
  } from '@/domain/tools'

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
  const standardProjectArtifacts = ref<TypedArtifact[]>([])
  const standardArtifactsLoading = ref(false)
  const selectedStandardArtifacts = reactive<Record<string, TypedArtifact | undefined>>({})
  const example = ref<ToolExample | null>(null)
  const applyingExample = ref(false)
  const previewOpen = ref(false)
  const previewLoading = ref(false)
  const preview = ref<ToolExampleFilePreview | null>(null)
  const exampleFiles = reactive<Record<string, FileUploadResponse | undefined>>({})
  const convertedFiles = reactive<Record<string, FileUploadResponse | undefined>>({})
  const sdfConversionLoading = reactive<Record<string, boolean>>({})
  const sdfConversionErrors = reactive<Record<string, string | undefined>>({})
  const documentationOpen = ref(false)

  const toolConfig = computed<Record<string, unknown> | undefined>(() => {
    const config = tool.value?.current_version?.config
    return config && typeof config === 'object'
      ? config as Record<string, unknown>
      : undefined
  })

  const toolValidationSummary = computed(() => getToolValidationSummary(toolConfig.value))
  const standardInputSlots = computed(() => resolveToolStandardInputSlots(tool.value))
  const standardParameterSchema = computed(() => resolveToolPackageParameterSchema(tool.value))
  const currentProjectId = computed(() => {
    const raw = route.query.project_id ?? route.query.projectId ?? route.params.projectId
    const value = Array.isArray(raw) ? raw[0] : raw
    return typeof value === 'string' && value.trim() ? value.trim() : undefined
  })

  // v2 工具优先使用 Tool Package 参数 schema；标准文件输入由 artifacts.inputs 单独绑定
  const inputSchema = computed<ToolSchema | undefined>(() => {
    if (standardParameterSchema.value) {
      return standardParameterSchema.value
    }

    const config = toolConfig.value
    if (config && typeof config === 'object' && 'input_schema' in config) {
      return config.input_schema as ToolSchema
    }
    return undefined
  })

  const outputSchema = computed<ToolSchema | undefined>(() => {
    const config = toolConfig.value
    if (config && typeof config === 'object' && 'output_schema' in config) {
      return config.output_schema as ToolSchema
    }
    return undefined
  })

  const outputGlobs = computed<string[]>(() => {
    const globs = toolConfig.value?.output_globs
    return Array.isArray(globs) ? globs.filter((item): item is string => typeof item === 'string') : []
  })

  const executorType = computed<string | undefined>(() => {
    const config = toolConfig.value
    if (config && typeof config === 'object' && 'type' in config && typeof config.type === 'string') {
      return config.type
    }
    return undefined
  })
  const isRemoteToolV1 = computed(() => {
    return toolConfig.value?.type === 'remote_api' && toolConfig.value?.mode === 'remote_tool_v1'
  })
  const remoteToolBaseUrl = computed(() => {
    const value = toolConfig.value?.base_url
    return typeof value === 'string' ? value : ''
  })
  const remoteToolManifestHash = computed(() => {
    const value = toolConfig.value?.manifest_sha256
    return typeof value === 'string' ? value : ''
  })
  const remoteToolLastSmokeTest = computed<Record<string, unknown> | undefined>(() => {
    const value = toolConfig.value?.last_smoke_test
    return value && typeof value === 'object' ? value as Record<string, unknown> : undefined
  })
  const remoteToolSmokeStatus = computed(() => {
    const status = remoteToolLastSmokeTest.value?.status
    return typeof status === 'string' ? status : 'not_run'
  })
  const remoteToolSmokeTaskId = computed(() => {
    const taskId = remoteToolLastSmokeTest.value?.task_id
    return typeof taskId === 'string' ? taskId : ''
  })
  const remoteToolSmokeError = computed(() => {
    const error = remoteToolLastSmokeTest.value?.error
    return typeof error === 'string' ? error : ''
  })

  const remoteToolSmokeStatusColor = (status: string) => {
    if (status === 'success') {
      return 'green'
    }
    if (status === 'failure') {
      return 'red'
    }
    if (status === 'scheduled') {
      return 'blue'
    }
    if (status === 'stale') {
      return 'orange'
    }
    return 'orange'
  }

  const remoteToolSmokeStatusText = (status: string) => {
    if (status === 'success') {
      return '已通过'
    }
    if (status === 'failure') {
      return '失败'
    }
    if (status === 'scheduled') {
      return '已排队'
    }
    if (status === 'stale') {
      return 'Manifest 已变更'
    }
    return '未完成'
  }

  // 扁平化并归一化 schema，隐藏平台内部字段并兼容 input_files / integer / nullable
  const flattenedSchema = computed<ToolSchema | undefined>(() => {
    return flattenToolInputSchema(inputSchema.value)
  })
  const selectedStandardArtifactRecord = computed<Record<string, TypedArtifact | undefined>>(() => {
    return Object.fromEntries(
      standardInputSlots.value.map(slot => [slot.name, selectedStandardArtifacts[slot.name]])
    )
  })
  const standardInputBindings = computed(() => {
    return buildStandardInputBindings(selectedStandardArtifactRecord.value)
  })
  const missingRequiredStandardSlots = computed(() => {
    return standardInputSlots.value.filter(
      slot => slot.required && !standardInputBindings.value[slot.name]
    )
  })

  const canSubmit = computed(() => {
    if (!userStore.isAuthenticated) return false
    if (Object.values(sdfConversionLoading).some(Boolean)) return false
    if (standardInputSlots.value.length && !currentProjectId.value) return false
    if (missingRequiredStandardSlots.value.length > 0) return false
    return true
  })
  const detailSubtitle = computed(() => {
    if (!tool.value) {
      return t('tools.detail')
    }

    return `${t('tools.usageCount')}: ${formatNumber(tool.value.statistics?.usage_count)} · ${t('tools.viewCount')}: ${formatNumber(tool.value.statistics?.view_count)}`
  })
  const documentationLabels = computed<ToolDocumentationLabels>(() => ({
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
    noDocumentation: t('tools.noDocumentation')
  }))
  const configuredDocumentationMarkdown = computed(() => {
    const markdown = toolConfig.value?.documentation_markdown
    return typeof markdown === 'string' ? markdown.trim() : ''
  })
  const documentationMarkdown = computed(() => {
    if (configuredDocumentationMarkdown.value) {
      return configuredDocumentationMarkdown.value
    }

    return buildFallbackToolDocumentation({
      toolName: tool.value?.name || t('tools.detail'),
      description: tool.value?.description,
      inputSchema: flattenedSchema.value,
      outputSchema: outputSchema.value,
      outputGlobs: outputGlobs.value,
      labels: documentationLabels.value
    })
  })
  const documentationHtml = computed(() => renderMarkdownToHtml(documentationMarkdown.value))

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

  const compatibleStandardArtifacts = (slot: StandardArtifactInputSlot) => {
    return filterCompatibleProjectArtifacts(slot, standardProjectArtifacts.value)
  }

  const handleStandardArtifactSelection = (slotName: string, versionId: unknown) => {
    const selectedVersionId = typeof versionId === 'string' ? versionId : undefined
    selectedStandardArtifacts[slotName] = selectedVersionId
      ? standardProjectArtifacts.value.find(
          artifact => artifact.latest_version.id === selectedVersionId
        )
      : undefined
  }

  const getFieldRules = (key: string, prop: SchemaProperty): Rule[] => {
    const rules: Rule[] = []
    const schema = flattenedSchema.value
    if (schema?.required?.includes(key)) {
      if (isFileSchemaProperty(prop)) {
        rules.push({
          validator: async () => {
            if (
              sdfConversionLoading[key] ||
              formState[key] ||
              fileList[key]?.length ||
              selectedArtifacts[key] ||
              exampleFiles[key] ||
              convertedFiles[key]
            ) {
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
    Object.keys(selectedStandardArtifacts).forEach(key => {
      selectedStandardArtifacts[key] = undefined
    })
    Object.keys(exampleFiles).forEach(key => {
      exampleFiles[key] = undefined
    })
    Object.keys(convertedFiles).forEach(key => {
      convertedFiles[key] = undefined
    })
    Object.keys(sdfConversionErrors).forEach(key => {
      sdfConversionErrors[key] = undefined
    })
  }

  const clearFieldValidation = (key: string) => {
    const form = formRef.value as (FormInstance & { clearValidate?: (names?: string[]) => void }) | undefined
    form?.clearValidate?.([key])
  }

  const getFileAccept = (key: string, prop: SchemaProperty): string | undefined => {
    return getToolFileAccept({ key, property: prop, toolSlug: tool.value?.slug })
  }

  const handleFileListChange = (key: string, files: UploadFile[]) => {
    fileList[key] = files
    if (files.length > 0) {
      const uploadedFile = files[0]!
      const rawFile = uploadedFile.originFileObj as File | undefined
      const filename = rawFile?.name || uploadedFile.name || ''
      if (showSdfToPdbConverter(key) && rawFile && filename.toLowerCase().endsWith('.sdf')) {
        fileList[key] = []
        formState[key] = undefined
        clearFieldValidation(key)
        void handleSdfToPdbConversion(key, rawFile)
        return
      }

      selectedArtifacts[key] = undefined
      exampleFiles[key] = undefined
      convertedFiles[key] = undefined
      sdfConversionErrors[key] = undefined
      formState[key] = uploadedFile?.uid ?? uploadedFile?.name
      clearFieldValidation(key)
      return
    }
    convertedFiles[key] = undefined
    sdfConversionErrors[key] = undefined
    formState[key] = undefined
  }

  const handleArtifactSelection = (key: string, artifact: ArtifactFile | null) => {
    selectedArtifacts[key] = artifact ?? undefined
    if (artifact) {
      fileList[key] = []
      exampleFiles[key] = undefined
      convertedFiles[key] = undefined
      sdfConversionErrors[key] = undefined
      formState[key] = artifact.id
      clearFieldValidation(key)
    } else {
      formState[key] = undefined
    }
  }

  const clearExampleFile = (key: string) => {
    exampleFiles[key] = undefined
    formState[key] = undefined
  }

  const clearConvertedFile = (key: string) => {
    convertedFiles[key] = undefined
    fileList[key] = []
    formState[key] = undefined
    sdfConversionErrors[key] = undefined
    void nextTick().then(() => formRef.value?.validateFields([key]).catch(() => undefined))
  }

  const createConvertedUploadFile = (file: FileUploadResponse): UploadFile => {
    return {
      uid: `converted-${file.id}`,
      name: file.filename,
      status: 'done',
      url: `/api/v1/files/${file.id}/download`
    }
  }

  const showSdfToPdbConverter = (key: string) => {
    return shouldShowSdfToPdbConverter(tool.value?.slug, key)
  }

  const sdfConversionStatusText = (key: string) => {
    return getSdfConversionStatusText({
      error: sdfConversionErrors[key],
      loading: sdfConversionLoading[key],
      convertedFilename: convertedFiles[key]?.filename
    })
  }

  const handleSdfToPdbConversion = async (key: string, file: File) => {
    if (!file.name.toLowerCase().endsWith('.sdf')) {
      message.warning('请上传 SDF 文件')
      return
    }

    sdfConversionLoading[key] = true
    sdfConversionErrors[key] = undefined
    clearFieldValidation(key)
    try {
      const res = await convertSdfToPdb(file)
      convertedFiles[key] = res.data
      fileList[key] = [createConvertedUploadFile(res.data)]
      selectedArtifacts[key] = undefined
      exampleFiles[key] = undefined
      formState[key] = res.data.id
      await nextTick()
      clearFieldValidation(key)
      message.success('SDF 已转换为 PDB')
    } catch (error) {
      convertedFiles[key] = undefined
      fileList[key] = []
      formState[key] = undefined
      sdfConversionErrors[key] = getToolRequestErrorMessage(error)
    } finally {
      sdfConversionLoading[key] = false
    }
  }

  const createSdfUploadBefore = (key: string) => {
    return (file: File) => {
      void handleSdfToPdbConversion(key, file)
      return false
    }
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

  const handleUseExample = async () => {
    if (!tool.value || !example.value) {
      return
    }

    if (!userStore.isLoggedIn) {
      message.warning(t('auth.loginRequired'))
      router.push('/login')
      return
    }

    applyingExample.value = true
    try {
      const res = await applyToolExample(tool.value.id)
      applyExampleParams(res.data.params)

      Object.entries(res.data.files).forEach(([field, file]) => {
        const formKey = resolveExampleFileFormKey(flattenedSchema.value, field)
        exampleFiles[formKey] = file
        fileList[formKey] = []
        selectedArtifacts[formKey] = undefined
        convertedFiles[formKey] = undefined
        formState[formKey] = file.id
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

    submitting.value = true
    try {
      const schema = flattenedSchema.value
      if (!schema) {
        message.error(t('common.noData'))
        return
      }
      if (standardInputSlots.value.length && !currentProjectId.value) {
        message.error('标准 Artifact 输入需要项目上下文，请从项目内进入工具。')
        return
      }
      if (missingRequiredStandardSlots.value.length) {
        message.error(`请选择标准 Artifact 输入：${missingRequiredStandardSlots.value.map(slot => slot.name).join(', ')}`)
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

      for (const [key, file] of Object.entries(convertedFiles)) {
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

      const taskPayload = {
        name: taskName.value.trim() || undefined,
        tool_id: tool.value!.id,
        params: payload.params,
        file_ids: payload.fileIds.length > 0 ? payload.fileIds : undefined,
        ...buildStandardRunTaskExtras({
          projectId: currentProjectId.value,
          inputBindings: standardInputBindings.value,
          standardInputUploads: {}
        })
      }

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
              convertedFiles[key] = undefined
              sdfConversionLoading[key] = false
              sdfConversionErrors[key] = undefined
            }
          }
        }
        for (const slot of standardInputSlots.value) {
          selectedStandardArtifacts[slot.name] = undefined
        }
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

  .standard-artifact-option {
    display: flex;
    flex-direction: column;
    gap: 2px;

    small {
      color: @text-color-light-tertiary;
      font-size: @font-size-sm;
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
