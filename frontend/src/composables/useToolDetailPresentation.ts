import { computed, unref, type Ref } from 'vue'
import type { Tool, ToolSchema } from '@/types/models'
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

  const outputSchema = computed<ToolSchema | undefined>(() => {
    const contractSchema = unref(options.tool)?.contract?.schema?.output
    if (contractSchema?.type === 'object' && contractSchema.properties) {
      return contractSchema
    }
    const schema = toolConfig.value?.output_schema
    return isRecord(schema) ? schema as unknown as ToolSchema : undefined
  })

  const outputGlobs = computed<string[]>(() => {
    const globs = toolConfig.value?.output_globs
    return Array.isArray(globs) ? globs.filter((item): item is string => typeof item === 'string') : []
  })

  const executorType = computed<string | undefined>(() => {
    const contractType = unref(options.tool)?.contract?.executor?.type
    if (contractType) return contractType
    const type = toolConfig.value?.type
    return typeof type === 'string' ? type : undefined
  })

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
    outputSchema,
    outputGlobs,
    executorType,
    detailSubtitle,
    documentationMarkdown,
    documentationHtml,
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}
