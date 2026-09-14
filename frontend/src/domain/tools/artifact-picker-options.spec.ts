import { describe, expect, it } from 'vitest'
import type { ArtifactFile } from '@/types/models'
import { buildArtifactPickerStepOptions } from './artifact-picker-options'
import type { ArtifactPickerLabels, ArtifactPickerTaskNode } from './artifact-file-picker'

const labels: ArtifactPickerLabels = {
  groupLabel: 'Group',
  toolLabel: 'Tool',
  taskLabel: 'Task',
  outputLabel: 'Output',
  selectGroup: 'Select group',
  selectTool: 'Select tool',
  selectTask: 'Select task',
  selectOutput: 'Select output',
  summarySelected: 'Selected',
  summaryFocused: 'Focused',
  summaryPending: 'Pending',
  ungroupedGroup: 'Ungrouped',
  groupMeta: 'Group meta',
  toolMeta: 'Tool meta',
  noArtifacts: 'No artifacts',
  noCompatibleArtifacts: 'No compatible artifacts',
  artifactSelectedTag: 'Selected',
  artifactFocusTag: 'Focused',
}

function artifact(overrides: Partial<ArtifactFile> = {}): ArtifactFile {
  return {
    id: 'artifact-1',
    filename: 'result.sdf',
    size_bytes: 1024,
    source_type: 'task_output',
    download_url: '/files/artifact-1',
    task_id: 'task-1',
    tool_id: 'tool-1',
    tool_name: 'Docking Tool',
    tool_slug: 'docking-tool',
    created_at: '2026-08-05T06:00:00Z',
    ...overrides,
  }
}

describe('artifact picker step options', () => {
  it('marks selected and focused artifacts for the panel', () => {
    const selectedArtifact = artifact({
      id: 'artifact-2',
      filename: 'picked.pdb',
    })
    const taskNode: ArtifactPickerTaskNode = {
      taskId: 'task-1',
      latestCreatedAt: '2026-08-05T06:00:00Z',
      artifacts: [artifact(), selectedArtifact],
    }

    const options = buildArtifactPickerStepOptions({
      activeStep: 'artifact',
      groupNodes: [],
      selectedGroupTools: [],
      selectedToolNode: null,
      selectedToolTasks: [taskNode],
      selectedTaskArtifacts: taskNode.artifacts,
      selectedTaskId: taskNode.taskId,
      selectedArtifact,
      focusedArtifactId: 'artifact-1',
      labels,
      formatTaskArtifactCount: (count) => `${count} outputs`,
    })

    expect(options).toEqual([
      expect.objectContaining({
        id: 'artifact-1',
        title: 'result.sdf',
        rightText: 'Focused',
        rightColor: 'gold',
        focused: true,
      }),
      expect.objectContaining({
        id: 'artifact-2',
        title: 'picked.pdb',
        rightText: 'Selected',
        rightColor: 'blue',
        selected: true,
      }),
    ])
  })
})
