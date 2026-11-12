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

  it('resolves an artifact-version snapshot that carries no file id back to a download url', async () => {
    const task = buildTask()
    task.input_snapshots = [
      {
        inputRole: 'RECEPTOR',
        // 真机数据就是这样：只有 URN，fileId 为空（早期写入没有回填文件 id）
        urn: 'artifact:3b558093-953a-4780-a47a-a0948ffa6e83',
        fileId: null,
        detail: { filename: 'prepared.pdb' },
      },
    ] as never

    const wrapper = mount(PocketComplexViewer, {
      props: { task: task as never },
      global: {
        plugins: [i18n],
        stubs: {
          MoleculeViewer: MoleculeViewerStub,
          'a-alert': { template: '<div data-testid="stub-alert" />' },
        },
      },
    })

    await flushPromises()

    const scene = wrapper.findComponent(MoleculeViewerStub).props('scene')
    expect(scene.entries).toHaveLength(2)
    expect(scene.entries[0]).toMatchObject({
      role: 'receptor',
      url: '/api/v1/artifacts/versions/3b558093-953a-4780-a47a-a0948ffa6e83/download',
      label: 'prepared.pdb',
    })
    expect(scene.entries[1]).toMatchObject({ role: 'pocket' })
  })

  it('resolves a file urn snapshot to the file download url', async () => {
    const task = buildTask()
    task.input_snapshots = [
      {
        inputRole: 'RECEPTOR',
        entityType: 'protein_structure',
        urn: 'file:479f3ae8-4373-459d-9e3c-b5573e96f151',
        fileId: null,
        detail: {},
      },
    ] as never

    const wrapper = mount(PocketComplexViewer, {
      props: { task: task as never },
      global: {
        plugins: [i18n],
        stubs: {
          MoleculeViewer: MoleculeViewerStub,
          'a-alert': { template: '<div data-testid="stub-alert" />' },
        },
      },
    })

    await flushPromises()

    const scene = wrapper.findComponent(MoleculeViewerStub).props('scene')
    expect(scene.entries[0].url).toBe(
      '/api/v1/files/479f3ae8-4373-459d-9e3c-b5573e96f151/download',
    )
  })

  it('prefers the snapshot whose filename looks like a structure, and never downloads candidates', async () => {
    // 历史快照可能把 fileId 记成版本 sidecar（metadata.json）。服务端读时已纠正，
    // 前端只按文件名做零成本筛选：不为了「猜哪条是坐标文件」去下载每个候选——
    // 那是把服务端的排序缺陷变成客户端的流量和首屏延迟。
    const task = buildTask()
    task.input_snapshots = [
      {
        inputRole: 'RECEPTOR',
        entityType: 'artifact_version',
        urn: 'artifact:1e429351-1b7f-4490-b535-72c9dc66b041',
        fileId: 'file-metadata',
        detail: { filename: 'metadata.json' },
      },
      {
        inputRole: 'RECEPTOR',
        entityType: 'protein_structure',
        urn: 'file:28fd57e1-8b5f-4492-83b2-40623ee60010',
        fileId: 'file-structure',
        detail: { filename: 'structure.pdb' },
      },
    ] as never

    const { fetchProtectedFileText } = await import('@/utils/protected-file-access')
    vi.mocked(fetchProtectedFileText).mockClear()

    const wrapper = mount(PocketComplexViewer, {
      props: { task: task as never },
      global: {
        plugins: [i18n],
        stubs: {
          MoleculeViewer: MoleculeViewerStub,
          'a-alert': { template: '<div data-testid="stub-alert" />' },
        },
      },
    })

    await flushPromises()

    const scene = wrapper.findComponent(MoleculeViewerStub).props('scene')
    expect(scene.entries.map((entry: { role: string }) => entry.role)).toEqual([
      'receptor',
      'pocket',
    ])
    expect(scene.entries[0].url).toBe('/api/v1/files/file-structure/download')

    // 只允许为「解析体素格」下载口袋文件；受体候选一个都不许下载。
    const downloaded = vi.mocked(fetchProtectedFileText).mock.calls.map(([url]) => String(url))
    expect(downloaded).toEqual(['/api/v1/files/file-pocket/download'])
  })
})
