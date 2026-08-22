export type StandardRunOutputScope = 'project' | 'default_workspace' | 'file_only'

export interface StandardRunContextInput {
  projectId?: string | null
  emitsStandardArtifacts?: boolean
}

export interface StandardRunContext {
  projectId?: string
  outputScope: StandardRunOutputScope
}

export interface StandardRunTaskExtrasInput {
  projectId?: string | null
  inputBindings: Record<string, string>
  standardInputUploads: Record<string, string>
}

export interface StandardRunTaskExtras {
  project_id?: string
  input_bindings?: Record<string, string>
  standard_input_uploads?: Record<string, string>
}

function compactRecord(value: Record<string, string>): Record<string, string> {
  return Object.fromEntries(
    Object.entries(value).filter(([, item]) => typeof item === 'string' && item.trim())
  )
}

export function resolveStandardRunContext(input: StandardRunContextInput): StandardRunContext {
  const projectId = input.projectId?.trim() || undefined
  return {
    projectId,
    outputScope: projectId
      ? 'project'
      : input.emitsStandardArtifacts
        ? 'default_workspace'
        : 'file_only',
  }
}

export function hasProjectScopedArtifactBindings(inputBindings: Record<string, string>): boolean {
  return Object.keys(compactRecord(inputBindings)).length > 0
}

export function buildStandardRunTaskExtras(input: StandardRunTaskExtrasInput): StandardRunTaskExtras {
  const projectId = input.projectId?.trim()
  const inputBindings = compactRecord(input.inputBindings)
  const standardInputUploads = compactRecord(input.standardInputUploads)

  return {
    ...(projectId ? { project_id: projectId } : {}),
    ...(Object.keys(inputBindings).length ? { input_bindings: inputBindings } : {}),
    ...(Object.keys(standardInputUploads).length
      ? { standard_input_uploads: standardInputUploads }
      : {}),
  }
}
