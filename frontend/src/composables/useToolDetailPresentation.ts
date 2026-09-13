import { computed, unref, type Ref } from 'vue'
import type { Tool, ToolSchema } from '@/types/models'
import { getToolValidationSummary } from '@/utils/tool-validation'
import {
  buildFallbackToolDocumentation,
  formatToolMetricCount,
  renderMarkdownToHtml,
  type ToolDocumentationLabels,
} from '@/domain/tools'

type MaybeRef<T> = T | Ref<T>

export interface ToolDetailPresentationLabels extends ToolDocumentationLabels {
  detailFallback: string
  usageCount: string
  viewCount: string
}

export interface ToolDetailPresentationOptions {
  tool: MaybeRef<Tool | null | undefined>
  inputSchema: MaybeRef<ToolSchema | undefined>
  labels: MaybeRef<ToolDetailPresentationLabels>
}

export function useToolDetailPresentation(options: ToolDetailPresentationOptions) {
  const toolConfig = computed<Record<string, unknown> | undefined>(() => {
    const config = unref(options.tool)?.current_version?.config
    return isRecord(config) ? config : undefined
  })

  const toolValidationSummary = computed(() => getToolValidationSummary(toolConfig.value))

  const outputSchema = computed<ToolSchema | undefined>(() => {
    const schema = toolConfig.value?.output_schema
    return isRecord(schema) ? schema as unknown as ToolSchema : undefined
  })

  const outputGlobs = computed<string[]>(() => {
    const globs = toolConfig.value?.output_globs
    return Array.isArray(globs) ? globs.filter((item): item is string => typeof item === 'string') : []
  })

  const executorType = computed<string | undefined>(() => {
    const type = toolConfig.value?.type
    return typeof type === 'string' ? type : undefined
  })

  const isRemoteToolV1 = computed(() => {
    return toolConfig.value?.type === 'remote_api' && toolConfig.value?.mode === 'remote_tool_v1'
  })

  const remoteToolBaseUrl = computed(() => stringValue(toolConfig.value?.base_url))
  const remoteToolManifestHash = computed(() => stringValue(toolConfig.value?.manifest_sha256))

  const remoteToolLastSmokeTest = computed<Record<string, unknown> | undefined>(() => {
    const value = toolConfig.value?.last_smoke_test
    return isRecord(value) ? value : undefined
  })

  const remoteToolSmokeStatus = computed(() => stringValue(remoteToolLastSmokeTest.value?.status) || 'not_run')
  const remoteToolSmokeTaskId = computed(() => stringValue(remoteToolLastSmokeTest.value?.task_id))
  const remoteToolSmokeError = computed(() => stringValue(remoteToolLastSmokeTest.value?.error))

  const detailSubtitle = computed(() => {
    const currentTool = unref(options.tool)
    const labels = unref(options.labels)
    if (!currentTool) {
      return labels.detailFallback
    }

    return `${labels.usageCount}: ${formatToolMetricCount(currentTool.statistics?.usage_count)} · ${labels.viewCount}: ${formatToolMetricCount(currentTool.statistics?.view_count)}`
  })

  const configuredDocumentationMarkdown = computed(() => {
    const markdown = toolConfig.value?.documentation_markdown
    return typeof markdown === 'string' ? markdown.trim() : ''
  })

  const documentationMarkdown = computed(() => {
    const configuredMarkdown = configuredDocumentationMarkdown.value
    const labels = unref(options.labels)
    if (configuredMarkdown) {
      return configuredMarkdown
    }

    const currentTool = unref(options.tool)
    return buildFallbackToolDocumentation({
      toolName: currentTool?.name || labels.detailFallback,
      description: currentTool?.description,
      inputSchema: unref(options.inputSchema),
      outputSchema: outputSchema.value,
      outputGlobs: outputGlobs.value,
      labels,
    })
  })

  const documentationHtml = computed(() => renderMarkdownToHtml(documentationMarkdown.value))

  return {
    toolConfig,
    toolValidationSummary,
    outputSchema,
    outputGlobs,
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
    documentationMarkdown,
    documentationHtml,
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

function stringValue(value: unknown): string {
  return typeof value === 'string' ? value : ''
}

function remoteToolSmokeStatusColor(status: string) {
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

function remoteToolSmokeStatusText(status: string) {
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
