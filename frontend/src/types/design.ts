/**
 * P-15 / P-16 / P-17 设计页（分子生成 / 多肽设计 / 生成结果）的类型定义。
 *
 * 字段名严格对齐后端契约：
 * - 工具 slug 与已部署的工具包一致（`pocket2mol-pocket-ligand-generation` /
 *   `therapainter-peptide-prediction`），见 `docs/06-UI交互与原型说明.md` 与 `docs/05-API接口规格说明书.md`。
 * - 结果读取复用 `GET /api/v1/results/{task_id}` 的既有 `ProjectResultDetail` 结构，
 *   这里只补上契约规定的 `mock` 布尔标记。
 */
import type { ProjectResultDetail } from '@/types/compounds'
import type { Tool, ToolVersion } from '@/types/models'

/** P-15 分子生成工具 slug（契约冻结，不可改）。 */
export const MOLECULE_GENERATION_TOOL_SLUG = 'pocket2mol-pocket-ligand-generation'
/** P-16 多肽设计工具 slug（契约冻结，不可改）。 */
export const PEPTIDE_DESIGN_TOOL_SLUG = 'therapainter-peptide-prediction'
/** 生成结果表产物的标准类型前缀（`molecule_table@1`）。 */
export const MOLECULE_TABLE_TYPE_PREFIX = 'molecule_table'
/** 结果表 SQL/产物下载主文件角色（见 `molecule_table@1` 标准）。 */
export const MOLECULE_TABLE_FILE_ROLE = 'table_file'

/** slug 解析后的工具与版本（提交任务时两者都需要）。 */
export interface ResolvedDesignTool {
  tool: Tool
  version: ToolVersion
}

/** P-15 参数（与 mock 包 `tool.yaml` 的 input schema 对齐）。 */
export interface MoleculeGenerationParams {
  num_molecules: number
  mw_min: number
  mw_max: number
  logp_min: number
  logp_max: number
  seed: number
}

/** P-16 参数（与 mock 包 `tool.yaml` 的 input schema 对齐）。 */
export interface PeptideDesignParams {
  num_peptides: number
  length_min: number
  length_max: number
  seed: number
}

/** 提交任务的载荷（页面构造，`api/design.ts` 转成 `TaskCreateParams`）。 */
export interface DesignTaskSubmission {
  name?: string
  projectId: string
  toolId: string
  toolVersionId?: string
  params: Record<string, number>
  inputBindings?: Record<string, string>
  standardInputUploads?: Record<string, string>
}

/** 口袋选择的完整下钻链路结果。 */
export interface DesignPocketSelection {
  projectId: string
  targetId: string
  proteinId: string
  structureId: string
  pocketId: string
  pocketLabel: string
  score: number | null
}

/** 结果详情 + 契约里的 `mock` 标记。 */
export interface DesignGenerationResult extends ProjectResultDetail {
  mock: boolean
}

/** 解析后的表格列（`numeric` 用于限定可排序 / 可筛选的列）。 */
export interface DesignTableColumn {
  key: string
  title: string
  numeric: boolean
}

/** 解析后的表格行（`__rowKey` 为稳定的行标识，其余为 CSV 原始字符串单元格）。 */
export interface DesignTableRow {
  __rowKey: string
  [column: string]: string
}

/** 解析后的 CSV 表格。 */
export interface DesignTable {
  columns: DesignTableColumn[]
  rows: DesignTableRow[]
}

/** 从结果产物里定位到的 `molecule_table` 表文件。 */
export interface DesignArtifactTable {
  artifactId: string
  versionId: string
  semanticType: string | null
  standardType: string | null
  filename: string | null
}
