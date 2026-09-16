import { ref } from 'vue'
import {
  createToolCreateEditorState,
  mergeToolCreateEditorStatePatch,
  type ToolCreateEditorState,
} from '@/domain/tools'

export function useToolCreateEditorState(defaults = createToolCreateEditorState()) {
  const apiHeaderEntries = ref<ToolCreateEditorState['apiHeaderEntries']>([
    ...defaults.apiHeaderEntries,
  ])
  const dockerCommandItems = ref<ToolCreateEditorState['dockerCommandItems']>([
    ...defaults.dockerCommandItems,
  ])
  const dockerEnvEntries = ref<ToolCreateEditorState['dockerEnvEntries']>([
    ...defaults.dockerEnvEntries,
  ])
  const pythonArgumentItems = ref<ToolCreateEditorState['pythonArgumentItems']>([
    ...defaults.pythonArgumentItems,
  ])
  const sshEnvEntries = ref<ToolCreateEditorState['sshEnvEntries']>([
    ...defaults.sshEnvEntries,
  ])
  const sshOutputGlobItems = ref<ToolCreateEditorState['sshOutputGlobItems']>([
    ...defaults.sshOutputGlobItems,
  ])

  function snapshot(): ToolCreateEditorState {
    return {
      apiHeaderEntries: apiHeaderEntries.value,
      dockerCommandItems: dockerCommandItems.value,
      dockerEnvEntries: dockerEnvEntries.value,
      pythonArgumentItems: pythonArgumentItems.value,
      sshEnvEntries: sshEnvEntries.value,
      sshOutputGlobItems: sshOutputGlobItems.value,
    }
  }

  function setState(editorState: ToolCreateEditorState): void {
    apiHeaderEntries.value = editorState.apiHeaderEntries
    dockerCommandItems.value = editorState.dockerCommandItems
    dockerEnvEntries.value = editorState.dockerEnvEntries
    pythonArgumentItems.value = editorState.pythonArgumentItems
    sshEnvEntries.value = editorState.sshEnvEntries
    sshOutputGlobItems.value = editorState.sshOutputGlobItems
  }

  function applyPatch(patch: Partial<ToolCreateEditorState>): void {
    setState(mergeToolCreateEditorStatePatch(snapshot(), patch))
  }

  return {
    apiHeaderEntries,
    dockerCommandItems,
    dockerEnvEntries,
    pythonArgumentItems,
    sshEnvEntries,
    sshOutputGlobItems,
    snapshot,
    applyPatch,
  }
}
