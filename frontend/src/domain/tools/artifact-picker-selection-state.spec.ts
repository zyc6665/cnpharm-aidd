import { describe, expect, it } from 'vitest'
import type { ArtifactFile } from '@/types/models'
import {
  applyArtifactPickerExternalSelectionPath,
  resolveArtifactPickerSelectionState,
} from './artifact-picker-selection-state'
import type { ArtifactPickerGroupNode } from './artifact-file-picker'

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

const groups: ArtifactPickerGroupNode[] = [
  {
    groupId: 'group-1',
    groupName: 'Group 1',
    tools: [
      {
        toolSlug: 'docking-tool',
        toolName: 'Docking Tool',
        tasks: [
          {
            taskId: 'task-1',
            latestCreatedAt: '2026-08-05T06:00:00Z',
            artifacts: [artifact()],
          },
        ],
      },
    ],
  },
  {
    groupId: 'group-2',
    groupName: 'Group 2',
    tools: [{ toolSlug: 'pocket-tool', toolName: 'Pocket Tool', tasks: [] }],
  },
]

describe('artifact picker selection state', () => {
  it('resolves selected artifact directly to the artifact step', () => {
    expect(resolveArtifactPickerSelectionState({
      groupNodes: groups,
      allowArtifacts: true,
      selectedArtifact: artifact(),
      currentState: { activeStep: 'group' },
    })).toEqual({
      activeStep: 'artifact',
      selectedGroupId: 'group-1',
      selectedToolSlug: 'docking-tool',
      selectedTaskId: 'task-1',
      focusedArtifactId: 'artifact-1',
    })
  })

  it('keeps valid path pieces and resets invalid deeper selections', () => {
    expect(resolveArtifactPickerSelectionState({
      groupNodes: groups,
      allowArtifacts: true,
      selectedArtifact: null,
      preferredGroupId: 'group-2',
      preferredToolSlug: 'pocket-tool',
      currentState: {
        activeStep: 'artifact',
        selectedGroupId: 'missing-group',
        selectedToolSlug: 'missing-tool',
        selectedTaskId: 'task-1',
        focusedArtifactId: 'artifact-1',
      },
    })).toEqual({
      activeStep: 'task',
      selectedGroupId: 'group-2',
      selectedToolSlug: 'pocket-tool',
    })
  })

  it('applies an external artifact path when every level is valid', () => {
    expect(applyArtifactPickerExternalSelectionPath({
      groupNodes: groups,
      allowArtifacts: true,
      currentState: { activeStep: 'group' },
      path: { token: 1, artifactId: 'artifact-1' },
    })).toEqual({
      activeStep: 'artifact',
      selectedGroupId: 'group-1',
      selectedToolSlug: 'docking-tool',
      selectedTaskId: 'task-1',
      focusedArtifactId: 'artifact-1',
    })
  })
})
