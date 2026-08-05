import type { SchemaProperty } from '@/types/models'

const SDF_TO_PDB_TOOL_SLUG = 'msign-affinity-prediction'
const SDF_CONVERSION_FALLBACK_ERROR = 'SDF 转 PDB 失败，请检查文件格式或后端转换服务'

export interface ToolFileAcceptOptions {
  key: string
  property: SchemaProperty
  toolSlug?: string | null
}

export interface SdfConversionStatusOptions {
  error?: string
  loading?: boolean
  convertedFilename?: string
}

function getSchemaAccept(prop: SchemaProperty): string | undefined {
  const uiAccept = (prop as SchemaProperty & { 'ui:accept'?: unknown })['ui:accept']
  return typeof uiAccept === 'string' ? uiAccept : prop.accept
}

export function shouldShowSdfToPdbConverter(
  toolSlug: string | null | undefined,
  key: string
): boolean {
  return (
    toolSlug === SDF_TO_PDB_TOOL_SLUG &&
    (key === 'ligand_pdb' || key.endsWith('.ligand_pdb'))
  )
}

export function getToolFileAccept(options: ToolFileAcceptOptions): string | undefined {
  const accept = getSchemaAccept(options.property)
  if (!shouldShowSdfToPdbConverter(options.toolSlug, options.key)) {
    return accept
  }

  const tokens = new Set(
    (accept || '.pdb')
      .split(',')
      .map(item => item.trim())
      .filter(Boolean)
  )
  tokens.add('.sdf')
  return Array.from(tokens).join(',')
}

export function getSdfConversionStatusText(options: SdfConversionStatusOptions): string {
  if (options.error) {
    return options.error
  }
  if (options.loading) {
    return '正在转换 SDF，请稍候...'
  }
  if (options.convertedFilename) {
    return `转换成功，已生成 ${options.convertedFilename}`
  }
  return ''
}

export function getToolRequestErrorMessage(error: unknown): string {
  const responseMessage = (error as { response?: { data?: { message?: unknown } } })?.response
    ?.data?.message
  if (typeof responseMessage === 'string' && responseMessage.trim()) {
    return responseMessage
  }

  const message = (error as { message?: unknown })?.message
  return typeof message === 'string' && message.trim() ? message : SDF_CONVERSION_FALLBACK_ERROR
}
