import { describe, expect, it } from 'vitest'
import type { ArtifactFile } from '@/types/models'
import {
  buildArtifactPickerViewModel,
  findArtifactPickerLocation,
  formatArtifactPickerArtifactMeta,
  formatArtifactPickerTaskMeta,
  resolveArtifactPickerPreferredGroupId,
  resolveArtifactPickerPreferredToolSlug,
} from './artifact-file-picker'

const labels = {
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

const groups = [
  {
    groupId: 'group-1',
    groupName: 'Group 1',
    groupSlug: 'group-1',
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
    groupSlug: 'group-2',
    tools: [{ toolSlug: 'pocket-tool', toolName: 'Pocket Tool', tasks: [] }],
  },
]

describe('artifact file picker rules', () => {
  it('formats artifact and task meta text', () => {
    const firstTask = groups[0]!.tools[0]!.tasks[0]!

    expect(formatArtifactPickerArtifactMeta(artifact())).toMatch(
      /^Docking Tool · \d{4}-\d{2}-\d{2} \d{2}:\d{2}$/
    )
    expect(formatArtifactPickerTaskMeta(firstTask, 'Docking Tool')).toMatch(
      /^Docking Tool · \d{4}-\d{2}-\d{2} \d{2}:\d{2}$/
    )
    expect(formatArtifactPickerTaskMeta(firstTask)).toMatch(/^-/)
  })

  it('finds an artifact location in the four-level hierarchy', () => {
    expect(findArtifactPickerLocation(groups, 'artifact-1')).toEqual({
      groupId: 'group-1',
      toolSlug: 'docking-tool',
      taskId: 'task-1',
    })
    expect(findArtifactPickerLocation(groups, 'missing')).toBeNull()
  })

  it('resolves preferred group and tool only when available', () => {
    const firstGroup = groups[0]!

    expect(resolveArtifactPickerPreferredGroupId(groups, 'group-2')).toBe('group-2')
    expect(resolveArtifactPickerPreferredGroupId(groups, 'missing')).toBe('group-1')
    expect(resolveArtifactPickerPreferredToolSlug(firstGroup, null, 'docking-tool')).toBe(
      'docking-tool'
    )
    expect(resolveArtifactPickerPreferredToolSlug(firstGroup, 'missing', 'other')).toBeUndefined()
  })

  it('builds path, step, and summary view model from selection state', () => {
    const selectedArtifact = artifact({ filename: 'picked.sdf' })

    const viewModel = buildArtifactPickerViewModel({
      groupNodes: groups,
      activeStep: 'artifact',
      selectedGroupId: 'group-1',
      selectedToolSlug: 'docking-tool',
      selectedTaskId: 'task-1',
      focusedArtifactId: 'artifact-1',
      selectedArtifact,
      labels,
    })

    expect(viewModel.selectedGroupTools).toHaveLength(1)
    expect(viewModel.selectedToolTasks).toHaveLength(1)
    expect(viewModel.selectedTaskArtifacts).toHaveLength(1)
    expect(viewModel.compatibleArtifacts).toHaveLength(1)
    expect(viewModel.currentStep).toEqual({
      label: 'Output',
      title: 'Select output',
      count: 1,
    })
    expect(viewModel.pathSegments.map(segment => ({
      step: segment.step,
      value: segment.value,
      complete: segment.complete,
    }))).toEqual([
      { step: 'group', value: 'Group 1', complete: true },
      { step: 'tool', value: 'Docking Tool', complete: true },
      { step: 'task', value: '#task-1', complete: true },
      { step: 'artifact', value: 'picked.sdf', complete: true },
    ])
    expect(viewModel.summary).toMatchObject({
      label: 'Selected',
      title: 'picked.sdf',
    })
    expect(viewModel.summary.meta).toContain('Docking Tool')
  })

  it('keeps pending summary anchored to the deepest selected level', () => {
    const viewModel = buildArtifactPickerViewModel({
      groupNodes: groups,
      activeStep: 'task',
      selectedGroupId: 'group-1',
      selectedToolSlug: 'docking-tool',
      selectedTaskId: undefined,
      focusedArtifactId: undefined,
      selectedArtifact: null,
      labels,
    })

    expect(viewModel.currentStep).toEqual({
      label: 'Task',
      title: 'Select task',
      count: 1,
    })
    expect(viewModel.summary).toEqual({
      label: 'Pending',
      title: 'Docking Tool',
      meta: 'Tool meta',
    })
  })

})
