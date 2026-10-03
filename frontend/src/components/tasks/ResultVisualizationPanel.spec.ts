import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import ResultVisualizationPanel from './ResultVisualizationPanel.vue'
import type { Task } from '@/types/models'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({
    t: (key: string) => key,
  }),
}))

const stubs = {
  AAlert: {
    props: ['message', 'description'],
    template: '<div data-testid="alert">{{ message }}{{ description }}</div>',
  },
  ATag: { template: '<span><slot /></span>' },
  ArtifactRenderer: {
    props: ['artifact'],
    template: '<div data-testid="artifact-preview">{{ artifact.name }}</div>',
  },
  CsvResultViewer: {
    props: ['file'],
    template: '<div data-testid="csv-preview">{{ file.filename }}</div>',
  },
  ResultFilePreview: {
    props: ['file', 'previewKind'],
    template: '<div data-testid="file-preview" :data-kind="previewKind">{{ file.filename }}</div>',
  },
  MoleculeViewer: {
    props: ['scene'],
    template: '<div data-testid="molecule-preview" :data-url="scene.entries[scene.entries.length - 1].url" />',
  },
}

function makeTask(outputFiles: NonNullable<Task['output_files']>): Task {
  return {
    id: 'task-1',
    tool_id: 'tool-1',
    status: 'success',
    progress: 100,
    created_at: '2026-10-02T00:00:00Z',
    output_files: outputFiles,
  }
}

function makeRunReportArtifact() {
  return {
    id: 'artifact-1',
    project_id: 'project-1',
    artifact_type: 'run_report',
    semantic_type: 'run_report',
    name: '运行报告',
    latest_version: {
      id: 'version-1',
      version: 1,
      filename: 'report.json',
      content_type: 'application/json',
      size_bytes: 128,
      sha256: 'a'.repeat(64),
      status: 'available',
      created_at: '2026-10-02T00:00:00Z',
    },
    created_at: '2026-10-02T00:00:00Z',
    updated_at: '2026-10-02T00:00:00Z',
  }
}

describe('ResultVisualizationPanel', () => {
  it('keeps structure and CSV outputs in one selectable result list', async () => {
    const wrapper = mount(ResultVisualizationPanel, {
      props: {
        task: makeTask([
          { id: 'structure-1', filename: 'ligand.pdb', url: '/files/ligand.pdb' },
          { id: 'table-1', filename: 'predictions.csv', url: '/files/predictions.csv' },
        ]),
      },
      global: { stubs },
    })

    const resultItems = wrapper.findAll('[data-testid="visualization-result-item"]')
    expect(resultItems).toHaveLength(2)

    await wrapper.get('[data-result-kind="csv"]').trigger('click')

    expect(wrapper.get('[data-testid="csv-preview"]').text()).toContain('predictions.csv')
    expect(wrapper.find('[data-testid="molecule-preview"]').exists()).toBe(false)
  })

  it('moves through visualization results with previous and next buttons', async () => {
    const wrapper = mount(ResultVisualizationPanel, {
      props: {
        task: makeTask([
          { id: 'structure-1', filename: 'ligand-1.pdb', url: '/files/ligand-1.pdb' },
          { id: 'structure-2', filename: 'ligand-2.pdb', url: '/files/ligand-2.pdb' },
        ]),
      },
      global: { stubs },
    })

    expect(wrapper.get('[data-testid="visualization-result-position"]').text()).toBe('1 / 2')
    expect(wrapper.get('[data-testid="molecule-preview"]').attributes('data-url')).toBe(
      '/files/ligand-1.pdb'
    )

    await wrapper.get('[data-testid="visualization-result-next"]').trigger('click')

    expect(wrapper.get('[data-testid="visualization-result-position"]').text()).toBe('2 / 2')
    expect(wrapper.get('[data-testid="molecule-preview"]').attributes('data-url')).toBe(
      '/files/ligand-2.pdb'
    )
  })

  it('does not hide file results when typed artifacts are also present', () => {
    const wrapper = mount(ResultVisualizationPanel, {
      props: {
        task: {
          ...makeTask([
            { id: 'structure-1', filename: 'receptor.pdb', url: '/files/receptor.pdb' },
            { id: 'table-1', filename: 'predictions.csv', url: '/files/predictions.csv' },
          ]),
          artifacts: [makeRunReportArtifact()],
        } as Task,
      },
      global: { stubs },
    })

    expect(wrapper.findAll('[data-testid="visualization-result-item"]')).toHaveLength(3)
    expect(wrapper.find('[data-result-kind="csv"]').exists()).toBe(true)
    expect(wrapper.find('[data-result-kind="artifact"]').exists()).toBe(true)
  })

  it('shows generic output files in the same result browser', async () => {
    const wrapper = mount(ResultVisualizationPanel, {
      props: {
        task: makeTask([
          { id: 'metadata-1', filename: 'metadata.json', url: '/files/metadata.json' },
          { id: 'binary-1', filename: 'model.bin', url: '/files/model.bin' },
        ]),
      },
      global: { stubs },
    })

    expect(wrapper.findAll('[data-testid="visualization-result-item"]')).toHaveLength(2)
    expect(wrapper.find('[data-result-kind="file"]').exists()).toBe(true)

    await wrapper.get('[data-result-kind="file"]').trigger('click')

    expect(wrapper.get('[data-testid="file-preview"]').attributes('data-kind')).toBe('json')
  })
})
