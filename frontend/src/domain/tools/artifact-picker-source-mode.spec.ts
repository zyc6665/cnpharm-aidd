import { describe, expect, it } from 'vitest'
import {
  resolveArtifactPickerActiveSourceMode,
  resolveArtifactPickerSyncedSourceMode,
} from './artifact-picker-source-mode'

describe('artifact picker source mode', () => {
  it('forces active mode when only one source type is available', () => {
    expect(resolveArtifactPickerActiveSourceMode({
      allowArtifacts: true,
      allowUploads: false,
      sourceMode: 'upload',
    })).toBe('artifact')

    expect(resolveArtifactPickerActiveSourceMode({
      allowArtifacts: false,
      allowUploads: true,
      sourceMode: 'artifact',
    })).toBe('upload')
  })

  it('keeps the current active mode when both source types are available', () => {
    expect(resolveArtifactPickerActiveSourceMode({
      allowArtifacts: true,
      allowUploads: true,
      sourceMode: 'artifact',
    })).toBe('artifact')
  })

  it('syncs selected artifacts back to artifact mode', () => {
    expect(resolveArtifactPickerSyncedSourceMode({
      allowArtifacts: true,
      allowUploads: true,
      hasSelectedArtifact: true,
    })).toBe('artifact')
  })

  it('defaults sync mode to upload when no artifact is selected', () => {
    expect(resolveArtifactPickerSyncedSourceMode({
      allowArtifacts: true,
      allowUploads: true,
      hasSelectedArtifact: false,
    })).toBe('upload')
  })
})
