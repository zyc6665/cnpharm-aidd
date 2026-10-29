/**
 * P-15 / P-16 / P-17 设计页 API 封装。
 *
 * 设计原则（见计划文档「前端 API 契约」）：
 * - 页面只消费既有后端接口，不新增 REST 端点；本文件只是把既有 `api/*`
 *   组合成设计页需要的形状（不修改 tools.ts / tasks.ts / results.ts / request.ts）。
 * - 工具 slug → tool / version 的解析走 `GET /api/v1/tools?page_size=100`。
 * - 生成结果表走 `GET /api/v1/artifacts/{artifact_id}/versions/{version_id}/files/table_file/download`，
 *   用 papaparse 解析 CSV。
 */
import Papa from 'papaparse'
import { getAllProjectArtifacts } from '@/api/artifacts'
import { listProjects } from '@/api/projects'
import { getResult } from '@/api/results'
import { createTask } from '@/api/tasks'
import { getToolList, getToolVersions } from '@/api/tools'
import { getTarget, listPockets, listStructures, listTargets } from '@/api/targets'
import { fetchProtectedFileText } from '@/utils/protected-file-access'
import type { ApiResponse } from '@/types/api'
import type { ProjectResultDetail } from '@/types/compounds'
import type { Task, TaskCreateParams } from '@/types/models'
import type { ResearchProject } from '@/types/projects'
import type {
  PocketSummary,
  ProteinDetail,
  ProteinStructureDetail,
  TargetSummary,
} from '@/types/targets'
import type {
  DesignArtifactTable,
  DesignGenerationResult,
  DesignTable,
  DesignTableColumn,
  DesignTableRow,
  DesignTaskSubmission,
  ResolvedDesignTool,
} from '@/types/design'
import { MOLECULE_TABLE_FILE_ROLE, MOLECULE_TABLE_TYPE_PREFIX } from '@/types/design'

interface PapaParseModule {
  parse(
    input: string,
    config?: { skipEmptyLines?: boolean | 'greedy' }
  ): { data: unknown[] }
}

/** 解析工具 slug 对应的 tool 与 current_version（发布契约的唯一入口）。 */
export async function resolveToolBySlug(slug: string): Promise<ResolvedDesignTool | null> {
  const response = await getToolList({ page: 1, page_size: 100 })
  const tool = response.data.items.find((item) => item.slug === slug)
  if (!tool) {
    return null
  }

  let version = tool.current_version ?? null
  if (!version) {
    const versions = await getToolVersions(tool.id)
    version =
      versions.data.find((item) => item.is_active && !item.deprecated) ??
      versions.data[0] ??
      null
  }

  if (!version) {
    return null
  }

  return { tool, version }
}

/** 项目下拉（`GET /api/v1/projects`）。 */
export async function listDesignProjects(): Promise<ResearchProject[]> {
  const response = await listProjects()
  return response.data.items
}

/** 项目内靶点（下钻第一层）。 */
export async function listProjectTargets(projectId: string): Promise<TargetSummary[]> {
  const response = await listTargets(projectId, { page: 1, page_size: 100 })
  return response.data.items
}

/** 靶点下的蛋白（下钻第二层，`GET /targets/{id}` 携带 proteins）。 */
export async function loadTargetProteins(targetId: string): Promise<ProteinDetail[]> {
  const response = await getTarget(targetId)
  return response.data.proteins ?? []
}

/** 蛋白下的结构（下钻第三层）。 */
export async function listProteinStructures(proteinId: string): Promise<ProteinStructureDetail[]> {
  const response = await listStructures(proteinId)
  return response.data.items
}

/** 结构下的口袋（下钻第四层）。 */
export async function listStructurePockets(structureId: string): Promise<PocketSummary[]> {
  const response = await listPockets(structureId)
  return response.data.items
}

/**
 * 把选中的口袋解析成任务 `input_bindings.pocket`。
 *
 * 优先在项目产物中找 `binding_pocket` 且 manifest 指向该口袋的 artifact version；
 * 找不到时退化为直接使用口袋 id（mock 场景下后端允许宽松绑定）。
 * 这样即使真实数据链路尚未产出口袋 artifact，页面也能先跑通流程。
 */
export async function resolvePocketInputBinding(
  projectId: string,
  pocketId: string
): Promise<Record<string, string>> {
  try {
    const response = await getAllProjectArtifacts(projectId, {
      artifact_type: 'binding_pocket',
    })
    const match = response.data.items.find((artifact) => {
      const metadata = artifact.latest_version?.manifest_json?.metadata
      if (!metadata) {
        return false
      }
      const candidate = metadata.pocket_id ?? metadata.pocketId
      return typeof candidate === 'string' && candidate === pocketId
    })
    const versionId = match?.latest_version?.id
    if (versionId) {
      return { pocket: versionId }
    }
  } catch {
    // 产物列表不可用时不应阻断提交，退化为口袋 id。
  }
  return { pocket: pocketId }
}

/** 提交设计任务（`POST /api/v1/tasks`）。 */
export function submitDesignTask(input: DesignTaskSubmission): Promise<ApiResponse<Task>> {
  const payload: TaskCreateParams = {
    ...(input.name ? { name: input.name } : {}),
    project_id: input.projectId,
    tool_id: input.toolId,
    ...(input.toolVersionId ? { tool_version_id: input.toolVersionId } : {}),
    params: input.params,
    ...(input.inputBindings && Object.keys(input.inputBindings).length
      ? { input_bindings: input.inputBindings }
      : {}),
    ...(input.standardInputUploads && Object.keys(input.standardInputUploads).length
      ? { standard_input_uploads: input.standardInputUploads }
      : {}),
  }
  return createTask(payload)
}

/** 读取生成结果详情（`GET /api/v1/results/{task_id}`，含 `mock` 标记）。 */
export async function getDesignGenerationResult(
  taskId: string
): Promise<DesignGenerationResult> {
  const response = await getResult(taskId)
  return response.data as DesignGenerationResult
}

/** 从结果产物里定位 `molecule_table` 表文件（语义类型 / 标准类型 / 产物类型均可命中）。 */
export function findMoleculeTableArtifact(
  result: ProjectResultDetail
): DesignArtifactTable | null {
  const output = result.outputs.find((item) => {
    const semantic = item.semantic_type ?? ''
    const standard = item.standard_type ?? ''
    const artifactType = item.artifact_type ?? ''
    return (
      semantic.startsWith(MOLECULE_TABLE_TYPE_PREFIX) ||
      standard.startsWith(MOLECULE_TABLE_TYPE_PREFIX) ||
      artifactType.startsWith(MOLECULE_TABLE_TYPE_PREFIX)
    )
  })

  if (!output || !output.id || !output.version_id) {
    return null
  }

  return {
    artifactId: output.id,
    versionId: output.version_id,
    semanticType: output.semantic_type,
    standardType: output.standard_type,
    filename: output.filename,
  }
}

/** 构造 `table_file` 下载地址（不经过 axios，交给 fetchProtectedFileText 鉴权）。 */
export function buildArtifactTableFileUrl(table: DesignArtifactTable): string {
  return `/api/v1/artifacts/${table.artifactId}/versions/${table.versionId}/files/${MOLECULE_TABLE_FILE_ROLE}/download`
}

function isNumericCell(value: string): boolean {
  const trimmed = value.trim()
  if (!trimmed) {
    return false
  }
  return Number.isFinite(Number(trimmed))
}

function detectNumericColumn(rows: string[][], index: number): boolean {
  let seen = 0
  for (const row of rows) {
    const raw = (row[index] ?? '').trim()
    if (!raw) {
      continue
    }
    if (!isNumericCell(raw)) {
      return false
    }
    seen += 1
  }
  return seen > 0
}

function toMatrix(text: string): string[][] {
  const parser = Papa as PapaParseModule
  const normalized =
    text.includes('\n') || text.includes('\r')
      ? text
      : text.replace(/\\r\\n/g, '\n').replace(/\\n/g, '\n')
  const result = parser.parse(normalized, { skipEmptyLines: 'greedy' })
  return result.data
    .filter((row): row is unknown[] => Array.isArray(row))
    .map((row) => row.map((cell) => String(cell ?? '')))
}

/** 用 papaparse 解析生成的 CSV 表（首行为表头）。 */
export function parseDesignTableCsv(text: string): DesignTable {
  const matrix = toMatrix(text)
  if (matrix.length === 0) {
    return { columns: [], rows: [] }
  }

  const headerRow = matrix[0] ?? []
  const dataRows = matrix.slice(1)
  const columnCount = Math.max(headerRow.length, ...dataRows.map((row) => row.length), 0)

  const usedKeys = new Set<string>()
  const columns: DesignTableColumn[] = []
  for (let index = 0; index < columnCount; index += 1) {
    const originalKey = (headerRow[index] ?? '').replace(/^\uFEFF/, '').trim()
    const baseKey = originalKey || `column_${index + 1}`
    let key = baseKey
    let duplicate = 2
    while (usedKeys.has(key)) {
      key = `${baseKey}_${duplicate}`
      duplicate += 1
    }
    usedKeys.add(key)
    columns.push({
      key,
      title: originalKey || `Column ${index + 1}`,
      numeric: detectNumericColumn(dataRows, index),
    })
  }

  const rows: DesignTableRow[] = dataRows.map((row, rowIndex) => {
    const record: DesignTableRow = { __rowKey: String(rowIndex) }
    columns.forEach((column, columnIndex) => {
      record[column.key] = row[columnIndex] ?? ''
    })
    return record
  })

  return { columns, rows }
}

/** 下载并解析结果表 CSV。 */
export async function loadDesignTable(table: DesignArtifactTable): Promise<DesignTable> {
  const text = await fetchProtectedFileText(buildArtifactTableFileUrl(table))
  return parseDesignTableCsv(text)
}
