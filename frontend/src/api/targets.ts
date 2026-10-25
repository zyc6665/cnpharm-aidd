/**
 * 靶点结构域 API（P-06~P-11）。
 *
 * 约定：
 * - 全部请求走 `@/api/request`，并统一带 `{ silent: true, retry: 1 }`
 *   （列表/详情类可安全重试，写操作错误由页面就地呈现）。
 * - 路径不带 `/api/v1` 前缀，axios 实例的 `baseURL` 已是 `/api/v1`；
 *   只有 `structurePdbUrl` 返回浏览器可直接访问的完整路径。
 */
import { del, get, post, put } from '@/api/request'
import type {
  PaginatedTargets,
  PocketResidueList,
  PocketSummary,
  ProteinCreateInput,
  ProteinDetail,
  ProteinStructureDetail,
  StructureImportInput,
  StructurePdbManifest,
  StructurePredictInput,
  TargetCreateInput,
  TargetListParams,
  TargetSummary,
  TargetUpdateInput,
  TaskSubmission,
} from '@/types/targets'

const READ_OPTIONS = { silent: true, retry: 1 } as const

/** 结构准备入参（后端 `StructurePrepareRequest`）。 */
export interface StructurePrepareInput {
  tool_slug?: string
  params?: Record<string, string | number | boolean>
  priority?: 'low' | 'normal' | 'high'
}

/** GET /projects/{projectId}/targets */
export const listTargets = (projectId: string, params?: TargetListParams) =>
  get<PaginatedTargets, TargetListParams>(`/projects/${projectId}/targets`, params, READ_OPTIONS)

/** POST /projects/{projectId}/targets */
export const createTarget = (projectId: string, data: TargetCreateInput) =>
  post<TargetSummary>(`/projects/${projectId}/targets`, data, READ_OPTIONS)

/** GET /targets/{targetId} */
export const getTarget = (targetId: string) =>
  get<TargetSummary>(`/targets/${targetId}`, undefined, READ_OPTIONS)

/** PUT /targets/{targetId} */
export const updateTarget = (targetId: string, data: TargetUpdateInput) =>
  put<TargetSummary>(`/targets/${targetId}`, data, READ_OPTIONS)

/** DELETE /targets/{targetId} */
export const deleteTarget = (targetId: string) =>
  del<{ id: string }>(`/targets/${targetId}`, READ_OPTIONS)

/** POST /targets/{targetId}/proteins */
export const createProtein = (targetId: string, data: ProteinCreateInput) =>
  post<ProteinDetail>(`/targets/${targetId}/proteins`, data, READ_OPTIONS)

/** GET /proteins/{proteinId} */
export const getProtein = (proteinId: string) =>
  get<ProteinDetail>(`/proteins/${proteinId}`, undefined, READ_OPTIONS)

/** POST /proteins/{proteinId}/structures:predict → 任务提交回执（含 task_id） */
export const predictStructure = (proteinId: string, data: StructurePredictInput) =>
  post<TaskSubmission>(`/proteins/${proteinId}/structures:predict`, data, READ_OPTIONS)

/** POST /proteins/{proteinId}/structures:import */
export const importStructure = (proteinId: string, data: StructureImportInput) =>
  post<ProteinStructureDetail>(`/proteins/${proteinId}/structures:import`, data, READ_OPTIONS)

/** GET /proteins/{proteinId}/structures（后端返回 `{ items }`，非分页） */
export const listStructures = (proteinId: string) =>
  get<{ items: ProteinStructureDetail[] }>(
    `/proteins/${proteinId}/structures`,
    undefined,
    READ_OPTIONS
  )

/** GET /structures/{structureId}（含 pockets） */
export const getStructure = (structureId: string) =>
  get<ProteinStructureDetail>(`/structures/${structureId}`, undefined, READ_OPTIONS)

/** POST /structures/{structureId}:prepare → 任务提交回执（含 task_id） */
export const prepareStructure = (structureId: string, data: StructurePrepareInput = {}) =>
  post<TaskSubmission>(`/structures/${structureId}:prepare`, data, READ_OPTIONS)

/** GET /structures/{structureId}/pdb 的浏览器访问地址（浏览器直连文件下载）。 */
export const structurePdbUrl = (structureId: string): string =>
  `/api/v1/structures/${structureId}/pdb`

/** GET /structures/{structureId}/pdb（结构化文件清单，含临时签名 download_url） */
export const getStructurePdbManifest = (structureId: string) =>
  get<StructurePdbManifest>(`/structures/${structureId}/pdb`, undefined, READ_OPTIONS)

/** GET /structures/{structureId}/pockets → `{ items }` */
export const listPockets = (structureId: string) =>
  get<{ items: PocketSummary[] }>(`/structures/${structureId}/pockets`, undefined, READ_OPTIONS)

/** POST /structures/{structureId}/pockets:predict → 任务提交回执 */
export const predictPockets = (structureId: string, data: StructurePredictInput = {}) =>
  post<TaskSubmission>(`/structures/${structureId}/pockets:predict`, data, READ_OPTIONS)

/** GET /pockets/{pocketId}（含 residues） */
export const getPocket = (pocketId: string) =>
  get<PocketSummary>(`/pockets/${pocketId}`, undefined, READ_OPTIONS)

/** POST /pockets/{pocketId}:select */
export const selectPocket = (pocketId: string, selected: boolean) =>
  post<PocketSummary>(`/pockets/${pocketId}:select`, { selected }, READ_OPTIONS)

/** GET /pockets/{pocketId}/residues?key_only= */
export const listPocketResidues = (pocketId: string, keyOnly?: boolean) =>
  get<PocketResidueList>(
    `/pockets/${pocketId}/residues`,
    keyOnly === undefined ? undefined : { key_only: keyOnly },
    READ_OPTIONS
  )
