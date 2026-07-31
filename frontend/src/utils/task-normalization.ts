import type { Task, Tool } from '@/types/models'

function buildFallbackTool(task: Task): Tool | undefined {
  const toolName = task.tool_name || task.tool?.name
  const toolSlug = task.tool_slug || task.tool?.slug

  if (!toolName && !toolSlug) {
    return task.tool
  }

  return {
    id: task.tool_id,
    name: toolName || toolSlug || '',
    slug: toolSlug || task.tool_id,
    description: task.tool?.description,
    icon: task.tool?.icon,
    tags: task.tool?.tags || [],
    status: task.tool?.status || 'published',
    current_version_id: task.tool?.current_version_id,
    current_version: task.tool?.current_version,
    usage_count: task.tool?.usage_count || 0,
    view_count: task.tool?.view_count || 0,
    favorite_count: task.tool?.favorite_count || 0,
    statistics: task.tool?.statistics,
    gpu_required: task.tool?.gpu_required || false,
    gpu_memory_mb: task.tool?.gpu_memory_mb,
    timeout_sec: task.tool?.timeout_sec,
    owner_id: task.tool?.owner_id,
    is_favorited: task.tool?.is_favorited,
    created_at: task.tool?.created_at || task.created_at,
    updated_at: task.tool?.updated_at,
    version: task.tool?.version,
    run_count: task.tool?.run_count,
  }
}

export function normalizeTaskSummary(task: Task): Task {
  const normalizedTool = buildFallbackTool(task)

  return {
    ...task,
    name: task.name,
    tool_name: task.tool_name || normalizedTool?.name,
    tool_slug: task.tool_slug || normalizedTool?.slug,
    tool: normalizedTool,
  }
}

export function normalizeTaskSummaries(tasks: Task[]): Task[] {
  return tasks.map(normalizeTaskSummary)
}
