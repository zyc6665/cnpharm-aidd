import { describe, expect, it } from 'vitest'
import { DEFAULT_SSH_OUTPUT_GLOBS } from '@/domain/tools'
import { useToolCreateEditorState } from './useToolCreateEditorState'

describe('useToolCreateEditorState', () => {
  it('exposes default editor refs and snapshots current values', () => {
    const editor = useToolCreateEditorState()

    editor.apiHeaderEntries.value = [{ key: 'Authorization', value: 'Bearer token' }]
    editor.pythonArgumentItems.value = ['--input', 'protein.pdb']

    expect(editor.snapshot()).toEqual({
      apiHeaderEntries: [{ key: 'Authorization', value: 'Bearer token' }],
      dockerCommandItems: [],
      dockerEnvEntries: [],
      pythonArgumentItems: ['--input', 'protein.pdb'],
      sshEnvEntries: [],
      sshOutputGlobItems: DEFAULT_SSH_OUTPUT_GLOBS,
    })
  })

  it('applies partial patches without clearing unspecified refs', () => {
    const editor = useToolCreateEditorState()
    editor.dockerCommandItems.value = ['python', 'old.py']
    editor.sshEnvEntries.value = [{ key: 'OMP_NUM_THREADS', value: '4' }]

    editor.applyPatch({
      dockerCommandItems: ['python', 'new.py'],
      sshOutputGlobItems: [],
    })

    expect(editor.snapshot()).toMatchObject({
      dockerCommandItems: ['python', 'new.py'],
      sshEnvEntries: [{ key: 'OMP_NUM_THREADS', value: '4' }],
      sshOutputGlobItems: [],
    })
  })
})
