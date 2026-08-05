import type { Task } from '@/types/models'

export type TaskOutputFile = NonNullable<Task['output_files']>[number]

export function getTaskOutputDataEntries(outputData: unknown): [string, unknown][] {
  if (!outputData || typeof outputData !== 'object' || Array.isArray(outputData)) {
    return []
  }

  return Object.entries(outputData as Record<string, unknown>)
}

export function getTaskOutputFiles(task: Pick<Task, 'output_files'>): TaskOutputFile[] {
  return task.output_files ?? []
}

export function hasTaskOutputSummaryContent(
  outputData: unknown,
  outputFiles: TaskOutputFile[] = []
): boolean {
  return getTaskOutputDataEntries(outputData).length > 0 || outputFiles.length > 0
}
