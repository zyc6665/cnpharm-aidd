import { getToolList } from '@/api/tools'
import { createTask } from '@/api/tasks'
import type { Task } from '@/types/models'

/** 解析出的工具与版本。 */
export interface ResolvedTool {
  toolId: string
  toolVersionId?: string
}

/**
 * 按 slug 解析工具（既有 `GET /api/v1/tools` 接口，不新增端点）。
 * 找到后返回 tool_id 与 current_version_id。
 */
export async function resolveToolBySlug(slug: string): Promise<ResolvedTool> {
  const response = await getToolList({ search: slug, page_size: 100 })
  const tool = response.data.items.find(item => item.slug === slug)
  if (!tool) {
    throw new Error(`未找到工具: ${slug}`)
  }
  return { toolId: tool.id, toolVersionId: tool.current_version_id || undefined }
}

export interface SubmitToolTaskInput {
  toolSlug: string
  projectId?: string
  name?: string
  params: Record<string, unknown>
  standardInputUploads: Record<string, string>
}

/**
 * 提交任务（既有 `POST /api/v1/tasks`）。standard_input_uploads 映射
 * 输入名 → 文件 id，符合冻结合同 `{name, project_id, tool_id, tool_version_id, params, standard_input_uploads}`。
 */
export async function submitToolTask(input: SubmitToolTaskInput): Promise<Task> {
  const tool = await resolveToolBySlug(input.toolSlug)
  const response = await createTask({
    name: input.name,
    project_id: input.projectId,
    tool_id: tool.toolId,
    tool_version_id: tool.toolVersionId,
    params: input.params,
    standard_input_uploads: input.standardInputUploads
  })
  return response.data
}
