import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import WorkspaceArtifactPreview from './WorkspaceArtifactPreview.vue'
import type { WorkspaceArtifact } from '@/api/workspace'
import type { RecentWorkspaceArtifactRow } from '@/domain/workspace'
import type { TypedArtifact } from '@/types/artifacts'

const getArtifact = vi.fn()

vi.mock('@/api/artifacts', () => ({
  getArtifact: (...args: unknown[]) => getArtifact(...args),
  buildArtifactVersionDownloadUrl: (artifactId: string, versionId: string) =>
    `/api/v1/artifacts/${artifactId}/versions/${versionId}/download`
}))

vi.mock('@/utils/protected-file-access', () => ({
  triggerProtectedFileDownload: vi.fn(),
  fetchProtectedFileText: vi.fn(),
  createProtectedObjectUrl: vi.fn()
}))

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (key: string) => key })
}))

function row(sizeBytes: number): RecentWorkspaceArtifactRow {
  return {
    id: 'artifact-1',
    title: '分子表 · v2',
    typeLabel: '分子表',
    fileName: 'cb_data_result.csv',
    sizeBytes,
    updatedAt: '2026-07-30T00:00:00Z',
    downloadUrl: '/api/v1/artifacts/artifact-1/versions/version-1/download'
  }
}

function artifactWithFile(
  artifactType: TypedArtifact['artifact_type'],
  file: { role: string; filename: string; content_type?: string; size_bytes: number }
): TypedArtifact {
  return {
    id: 'artifact-1',
    project_id: 'project-1',
    artifact_type: artifactType,
    semantic_type: artifactType,
    name: 'machine_name',
    latest_version: {
      id: 'version-1',
      version: 2,
      filename: file.filename,
      content_type: file.content_type,
      size_bytes: file.size_bytes,
      sha256: 'a'.repeat(64),
      status: 'available',
      created_at: '2026-07-30T00:00:00Z',
      files: [
        {
          id: 'file-1',
          role: file.role,
          file_id: 'file-1',
          is_primary: true,
          sort_order: 0,
          filename: file.filename,
          content_type: file.content_type,
          size_bytes: file.size_bytes,
          sha256: 'a'.repeat(64),
          download_url: `/api/v1/artifacts/artifact-1/versions/version-1/files/${file.role}/download`
        }
      ]
    },
    created_at: '2026-07-30T00:00:00Z',
    updated_at: '2026-07-30T00:00:00Z'
  }
}

const stubs = {
  ADrawer: { props: ['open'], template: '<div v-if="open"><slot /></div>' },
  ASpin: { template: '<div><slot /></div>' },
  AButton: { template: '<button><slot /></button>' },
  DownloadOutlined: true,
  CsvResultViewer: {
    name: 'CsvResultViewer',
    props: ['file'],
    template: '<div data-testid="artifact-preview-csv">{{ file && file.filename }}</div>'
  },
  ResultFilePreview: {
    name: 'ResultFilePreview',
    props: ['file', 'previewKind'],
    template: '<div data-testid="file-stub">{{ previewKind }}</div>'
  },
  ArtifactRenderer: {
    name: 'ArtifactRenderer',
    props: ['artifact'],
    template: '<div data-testid="artifact-preview-structure">structure</div>'
  },
  MoleculeViewer: true
}

function render(rowValue: RecentWorkspaceArtifactRow) {
  const overviewArtifact = {
    id: 'artifact-1',
    artifact_type: 'molecule_table',
    semantic_type: 'molecule_table',
    name: rowValue.title,
    latest_version: {
      id: 'version-1',
      version: 2,
      filename: rowValue.fileName ?? '',
      size_bytes: rowValue.sizeBytes,
      sha256: 'a'.repeat(64),
      status: 'available',
      created_at: '2026-07-30T00:00:00Z'
    },
    created_at: '2026-07-30T00:00:00Z',
    updated_at: rowValue.updatedAt
  } as unknown as WorkspaceArtifact

  return mount(WorkspaceArtifactPreview, {
    props: { open: true, row: rowValue, artifact: overviewArtifact, legacyFile: null },
    global: { stubs }
  })
}

describe('WorkspaceArtifactPreview', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('CSV 产物打开表格预览，不触发下载', async () => {
    getArtifact.mockResolvedValue({
      data: artifactWithFile('molecule_table', {
        role: 'table_file',
        filename: 'cb_data_result.csv',
        content_type: 'text/csv',
        size_bytes: 3848
      })
    })
    const wrapper = render(row(3848))
    await flushPromises()

    expect(getArtifact).toHaveBeenCalledWith('artifact-1')
    expect(wrapper.find('[data-testid="artifact-preview-csv"]').text()).toBe('cb_data_result.csv')
    expect(wrapper.find('[data-testid="artifact-preview-download"]').exists()).toBe(true)
  })

  it('JSON 产物走结构化文件预览', async () => {
    getArtifact.mockResolvedValue({
      data: artifactWithFile('run_report', {
        role: 'report_json',
        filename: 'report.json',
        content_type: 'application/json',
        size_bytes: 343
      })
    })
    const wrapper = render(row(343))
    await flushPromises()

    expect(wrapper.find('[data-testid="artifact-preview-file"]').text()).toBe('json')
  })

  it('结构产物走三维结构预览', async () => {
    getArtifact.mockResolvedValue({
      data: artifactWithFile('protein_structure', {
        role: 'structure_file',
        filename: 'structure.pdb',
        content_type: 'application/octet-stream',
        size_bytes: 15227
      })
    })
    const wrapper = render(row(15227))
    await flushPromises()

    expect(wrapper.find('[data-testid="artifact-preview-structure"]').exists()).toBe(true)
  })

  it('超过 5MB 的文件只显示元信息与下载提示，不加载内容', async () => {
    const largeBytes = 6 * 1024 * 1024
    getArtifact.mockResolvedValue({
      data: artifactWithFile('md_trajectory', {
        role: 'topology_pdb',
        filename: 'topology.pdb',
        content_type: 'application/octet-stream',
        size_bytes: largeBytes
      })
    })
    const wrapper = render(row(largeBytes))
    await flushPromises()

    expect(wrapper.find('[data-testid="artifact-preview-too-large"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="artifact-preview-csv"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="artifact-preview-structure"]').exists()).toBe(false)
  })
})
