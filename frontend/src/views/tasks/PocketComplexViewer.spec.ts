import { describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import i18n from '@/locales'

vi.mock('@/utils/protected-file-access', () => ({
  fetchProtectedFileText: vi.fn(async () => (
    'ATOM      1  C   UNL     1      20.271   4.822  48.343  1.00  0.00           C\n' +
    'ATOM      2  C   UNL     1      22.271   4.822  48.343  1.00  0.00           C'
  )),
}))

import PocketComplexViewer from './PocketComplexViewer.vue'

const MoleculeViewerStub = {
  name: 'MoleculeViewer',
  props: ['scene', 'voxelGrid'],
  template: '<div data-testid="stub-molecule-viewer" />',
}

function buildTask() {
  return {
    id: 't1',
    tool_id: 'tool-1',
    status: 'success',
    progress: 100,
    created_at: '2026-11-06T00:00:00Z',
    input_snapshots: [
      {
        inputRole: 'RECEPTOR',
        fileId: 'file-protein',
        detail: { filename: 'egfr-1m17.pdb' },
      },
    ],
    output_files: [
      { id: 'file-residues', filename: 'protein_pocket_residues.pdb' },
      { id: 'file-pocket', filename: 'pocket0.pdb' },
    ],
  }
}

describe('PocketComplexViewer', () => {
  it('combines the receptor, pocket residues and pocket voxels', async () => {
    const wrapper = mount(PocketComplexViewer, {
      props: { task: buildTask() as never },
      global: {
        plugins: [i18n],
        stubs: {
          MoleculeViewer: MoleculeViewerStub,
          'a-alert': { template: '<div data-testid="stub-alert" />' },
        },
      },
    })

    await flushPromises()

    const viewer = wrapper.findComponent(MoleculeViewerStub)
    expect(viewer.exists()).toBe(true)
    expect(viewer.props('scene').entries.map((entry: { role: string }) => entry.role)).toEqual([
      'receptor',
      'pocket',
    ])
    expect(viewer.props('voxelGrid').boxes).toHaveLength(2)
  })
})
