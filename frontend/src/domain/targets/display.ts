/**
 * 靶点结构域的展示层计算。
 *
 * P-06~P-11 只负责编排，日期/置信度/来源文案与 3D 预览所需的
 * `TypedArtifact` 组装全部收敛在这里，便于单测覆盖。
 */
import { formatServerDateTime } from '@/utils/datetime'
import type { ArtifactVersionFile, TypedArtifact } from '@/types/artifacts'
import type {
  ProteinStructureDetail,
  StructureFileLink,
  ToolRef,
} from '@/types/targets'

/** 缺省占位符，保持与口袋域一致。 */
const PLACEHOLDER = '-'

/** 结构 3D 预览优先使用的文件角色（结构 → 准备后结构 → pdbqt）。 */
export const STRUCTURE_PREVIEW_FILE_ROLES: readonly string[] = ['structure', 'prepared', 'pdbqt']

const STRUCTURE_FILE_EXTENSION: Record<string, string> = {
  structure: '.pdb',
  prepared: '.pdb',
  pdbqt: '.pdbqt',
}

/** 文本占位：空串/null/undefined 一律显示 `-`。 */
export function formatOptionalText(value: string | null | undefined): string {
  if (typeof value !== 'string') {
    return PLACEHOLDER
  }
  const trimmed = value.trim()
  return trimmed.length > 0 ? trimmed : PLACEHOLDER
}

/** 时间戳展示（本地时间）；无法解析时回退为原始文本。 */
export function formatTargetDateTime(value: string | null | undefined): string {
  if (!value) {
    return PLACEHOLDER
  }
  return formatServerDateTime(value)
}

/** 平均 pLDDT 展示（保留两位小数）。 */
export function formatPlddtMean(value: number | null | undefined): string {
  return typeof value === 'number' && Number.isFinite(value) ? value.toFixed(2) : PLACEHOLDER
}

/** 模型/工具标识展示：`name version`，缺失时显示占位符。 */
export function formatToolRef(ref: ToolRef | null | undefined): string {
  if (!ref) {
    return PLACEHOLDER
  }
  const name = ref.name?.trim() ?? ''
  const version = ref.version?.trim() ?? ''
  if (name && version) {
    return `${name} ${version}`
  }
  if (name) {
    return name
  }
  return version || PLACEHOLDER
}

/** 按偏好角色挑一个可下载的结构文件；找不到返回 null。 */
export function pickStructureFile(
  files: readonly StructureFileLink[],
  preferredRoles: readonly string[] = STRUCTURE_PREVIEW_FILE_ROLES
): StructureFileLink | null {
  for (const role of preferredRoles) {
    const match = files.find((file) => file.role === role && file.download_url)
    if (match) {
      return match
    }
  }
  // 调用方给定的角色全部落空时，仍按默认优先级（结构 → 准备后 → pdbqt）兜底，
  // 避免因为清单顺序把 pdbqt 当成首选渲染。
  for (const role of STRUCTURE_PREVIEW_FILE_ROLES) {
    if (preferredRoles.includes(role)) {
      continue
    }
    const match = files.find((file) => file.role === role && file.download_url)
    if (match) {
      return match
    }
  }
  return files.find((file) => Boolean(file.download_url)) ?? null
}

function structureFileName(structureId: string, role: string): string {
  const extension = STRUCTURE_FILE_EXTENSION[role] ?? '.pdb'
  return `${structureId}-${role}${extension}`
}

/**
 * 把结构详情 + 文件清单组装成 `StructureArtifactPreview` 需要的 `TypedArtifact`。
 *
 * 后端 `GET /structures/{id}/pdb` 只返回 `{role, file_id, urn, download_url}`，
 * 不含文件名，因此这里按角色推断扩展名（structure/prepared → .pdb，pdbqt → .pdbqt）。
 */
export function buildStructurePreviewArtifact(
  structure: ProteinStructureDetail,
  files: readonly StructureFileLink[]
): TypedArtifact | null {
  const primary = pickStructureFile(files)
  if (!primary) {
    return null
  }

  const versionFiles: ArtifactVersionFile[] = files.map((file, index) => ({
    id: file.file_id,
    role: file.role,
    file_id: file.file_id,
    is_primary: file.file_id === primary.file_id,
    sort_order: index,
    filename: structureFileName(structure.id, file.role),
    content_type: null,
    size_bytes: null,
    sha256: structure.sha256,
    download_url: file.download_url,
  }))

  return {
    id: structure.id,
    project_id: '',
    artifact_type: 'protein_structure',
    semantic_type: 'protein_structure',
    name: structureFileName(structure.id, primary.role),
    description: null,
    latest_version: {
      id: structure.id,
      version: 1,
      filename: structureFileName(structure.id, primary.role),
      content_type: null,
      size_bytes: 0,
      sha256: structure.sha256 ?? '',
      status: 'ready',
      created_at: structure.created_at ?? '',
      files: versionFiles,
    },
    created_at: structure.created_at ?? '',
    updated_at: structure.updated_at ?? '',
  }
}

/** 结构文件角色的展示标签：后端给的是枚举名，原样透出。 */
export function formatSourceType(value: string | null | undefined): string {
  if (!value) {
    return PLACEHOLDER
  }
  return value
}

/**
 * 从请求异常里取用户可读的错误文案。
 *
 * 与 `domain/tools/detail-file-inputs.ts` 的 `getToolRequestErrorMessage` 同构：
 * axios 的原始 message 是 `Request failed with status code 400`，没有任何信息量；
 * 后端 `ApiResponse.message` 才是真正的业务原因（如「蛋白缺少序列，无法提交结构预测」）。
 */
export function resolveTargetErrorMessage(cause: unknown, fallback: string): string {
  const responseMessage = (cause as { response?: { data?: { message?: unknown } } })?.response?.data
    ?.message
  if (typeof responseMessage === 'string' && responseMessage.trim()) {
    return responseMessage.trim()
  }

  const message = (cause as { message?: unknown })?.message
  if (typeof message === 'string' && message.trim()) {
    return message.trim()
  }

  return fallback
}
