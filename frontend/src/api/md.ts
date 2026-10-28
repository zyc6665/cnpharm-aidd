/**
 * MD / 自由能页面数据访问层。
 *
 * 仅复用既有只读端点，不新增后端接口：
 * - 工具查询：`GET /tools`、`GET /tools/{id}/versions`
 * - 任务提交：`POST /tasks`
 * - 结果读取：`GET /results/{task_id}`
 * - 产物读取：`GET /artifacts/{id}`
 */

import { getArtifact } from './artifacts'
import { getResult } from './results'
import { createTask } from './tasks'
import { getToolDetail, getToolList, getToolVersions } from './tools'
import type { TypedArtifact } from '@/types/artifacts'
import type { ProjectResultDetail, ResultOutputArtifact } from '@/types/compounds'
import type { MdResultDetail, MdSubmitParams } from '@/types/md'
import type { Task, Tool, ToolVersion } from '@/types/models'

/** P-26 提交的 tool slug（冻结契约，勿改）。 */
export const MD_TOOL_SLUG = 'gromacs-md-simulation'

/** P-28 自由能任务的 tool slug（冻结契约，勿改）。 */
export const FREE_ENERGY_TOOL_SLUG = 'gmx-mmpbsa-free-energy'

/** P-27 轨迹产物标准类型前缀。 */
export const MD_TRAJECTORY_STANDARD_TYPE = 'md_trajectory@1'

/** P-28 自由能产物（`energies`）标准类型。 */
export const MOLECULE_TABLE_STANDARD_TYPE = 'molecule_table@1'

/** 在公开工具列表中按 slug 精确定位工具；找不到返回 null。 */
export async function findToolBySlug(slug: string): Promise<Tool | null> {
  const searched = await getToolList({ view: 'public', search: slug, page_size: 100 })
  const hit = searched.data.items.find((tool) => tool.slug === slug)
  if (hit) return hit

  // 搜索索引可能忽略 slug，退化为整表扫描一层。
  const all = await getToolList({ view: 'public', page_size: 100 })
  return all.data.items.find((tool) => tool.slug === slug) ?? null
}

/** 解析工具的可用版本 id（优先 current_version_id，其次活跃版本）。 */
export async function resolveToolVersionId(tool: Tool): Promise<string | undefined> {
  if (tool.current_version_id) return tool.current_version_id
  const versions: ToolVersion[] = (await getToolVersions(tool.id)).data
  const active = versions.find((version) => version.is_active && !version.deprecated)
  return (active ?? versions[0])?.id
}

/** 读取工具详情（含参数 schema，可用于渲染兜底提示）。 */
export async function getMdToolDetail(toolId: string): Promise<Tool> {
  return (await getToolDetail(toolId)).data
}

export interface SubmitMdTaskInput {
  projectId: string
  toolId: string
  toolVersionId?: string
  params: MdSubmitParams
  /** 已准备好的复合物结构文件 id（来自 structure 的 file 列表）。 */
  complexFileId: string
  name?: string
}

/** 提交 MD 任务，返回新任务 id。 */
export async function submitMdTask(input: SubmitMdTaskInput): Promise<string> {
  const response = await createTask({
    name: input.name,
    project_id: input.projectId,
    tool_id: input.toolId,
    tool_version_id: input.toolVersionId,
    params: { ...input.params },
    standard_input_uploads: { complex: input.complexFileId }
  })
  return response.data.id
}

/** 读取结果详情（MD 结果允许携带 mock 标记）。 */
export async function getMdResult(taskId: string): Promise<MdResultDetail> {
  const response = await getResult(taskId)
  return response.data as MdResultDetail
}

/** 读取单个产物的完整文件清单（TypedArtifact）。 */
export async function getArtifactDetail(artifactId: string): Promise<TypedArtifact> {
  return (await getArtifact(artifactId)).data
}

export type { Task, Tool, ToolVersion, ProjectResultDetail, ResultOutputArtifact }
