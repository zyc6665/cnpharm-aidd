export type ArtifactPickerSourceMode = 'upload' | 'artifact'

export interface ResolveArtifactPickerActiveSourceModeInput {
  allowArtifacts: boolean
  allowUploads: boolean
  sourceMode: ArtifactPickerSourceMode
}

export interface ResolveArtifactPickerSyncedSourceModeInput {
  allowArtifacts: boolean
  allowUploads: boolean
  hasSelectedArtifact: boolean
}

export function resolveArtifactPickerActiveSourceMode(
  input: ResolveArtifactPickerActiveSourceModeInput
): ArtifactPickerSourceMode {
  if (!input.allowUploads && input.allowArtifacts) {
    return 'artifact'
  }

  if (!input.allowArtifacts && input.allowUploads) {
    return 'upload'
  }

  return input.sourceMode
}

export function resolveArtifactPickerSyncedSourceMode(
  input: ResolveArtifactPickerSyncedSourceModeInput
): ArtifactPickerSourceMode {
  if (!input.allowArtifacts) {
    return 'upload'
  }

  if (!input.allowUploads) {
    return 'artifact'
  }

  return input.hasSelectedArtifact ? 'artifact' : 'upload'
}
