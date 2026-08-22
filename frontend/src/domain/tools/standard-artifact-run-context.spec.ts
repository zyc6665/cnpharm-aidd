import { describe, expect, it } from 'vitest'
import {
  buildStandardRunTaskExtras,
  hasProjectScopedArtifactBindings,
  resolveStandardRunContext,
} from './standard-artifact-run-context'

describe('standard artifact run context', () => {
  it('allows standard-output tools to run without explicit project', () => {
    expect(resolveStandardRunContext({ projectId: undefined, emitsStandardArtifacts: true })).toEqual({
      projectId: undefined,
      outputScope: 'default_workspace',
    })
  })

  it('uses explicit project scope when project id is present', () => {
    expect(resolveStandardRunContext({ projectId: ' project-1 ', emitsStandardArtifacts: true })).toEqual({
      projectId: 'project-1',
      outputScope: 'project',
    })
  })

  it('keeps non-standard-output runs file-only without project', () => {
    expect(resolveStandardRunContext({ projectId: undefined, emitsStandardArtifacts: false })).toEqual({
      projectId: undefined,
      outputScope: 'file_only',
    })
  })

  it('requires project scope only when binding existing ArtifactVersions', () => {
    expect(hasProjectScopedArtifactBindings({ protein: 'version-1' })).toBe(true)
    expect(hasProjectScopedArtifactBindings({ protein: '   ' })).toBe(false)
    expect(hasProjectScopedArtifactBindings({})).toBe(false)
  })

  it('serializes project bindings and staged uploads separately', () => {
    expect(buildStandardRunTaskExtras({
      projectId: ' project-1 ',
      inputBindings: { protein: 'version-1', empty: '' },
      standardInputUploads: { ligand: 'file-1', blank: '   ' },
    })).toEqual({
      project_id: 'project-1',
      input_bindings: { protein: 'version-1' },
      standard_input_uploads: { ligand: 'file-1' },
    })
  })

  it('omits empty optional task extras', () => {
    expect(buildStandardRunTaskExtras({
      projectId: undefined,
      inputBindings: {},
      standardInputUploads: {},
    })).toEqual({})
  })
})
