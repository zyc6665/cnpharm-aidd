import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import ArtifactRenderer from './ArtifactRenderer.vue'
import MessageTimeline from '@/components/conversation/MessageTimeline.vue'
import ResultVisualizationPanel from '@/components/tasks/ResultVisualizationPanel.vue'
import type { TypedArtifact } from '@/types/artifacts'
import type { ConversationMessage } from '@/types/conversations'
import type { Task } from '@/types/models'

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (key: string) => key })
}))

vi.mock('@/components/tasks/MoleculeViewer.vue', () => ({
  __esModule: true,
  default: {
    name: 'MoleculeViewer',
    props: ['scene'],
    template: '<div data-testid="molecule-viewer">{{ scene.entries[0].url }}</div>'
  }
}))

const version = {
  id: 'version-1',
  version: 1,
  filename: 'target.txt',
  content_type: 'text/plain',
  size_bytes: 2048,
  sha256: 'a'.repeat(64),
  status: 'available',
  created_at: '2026-07-30T00:00:00Z'
}

function artifact(overrides: Partial<TypedArtifact>): TypedArtifact {
  return {
    id: 'artifact-1',
    project_id: 'project-1',
    artifact_type: 'file',
    semantic_type: 'generic_file',
    name: 'target.pdb',
    description: '测试产物',
    latest_version: version,
    created_at: '2026-07-30T00:00:00Z',
    updated_at: '2026-07-30T00:00:00Z',
    ...overrides
  }
}

const stubs = {
  AAlert: {
    template: '<div class="a-alert"><slot />{{ message }}{{ description }}</div>',
    props: ['message', 'description']
  },
  AButton: { template: '<button><slot /></button>' },
  ADescriptions: { template: '<dl><slot /></dl>' },
  ADescriptionsItem: { template: '<div><slot /></div>' },
  AEmpty: true,
  ATag: { template: '<span><slot /></span>' },
  BranchesOutlined: true
}

describe('ArtifactRenderer', () => {
  it.each([
    ['protein_structure', 'protein-structure-artifact'],
    ['pocket_result', 'pocket-result-artifact'],
    ['file', 'file-artifact'],
    ['run_report', 'run-report-artifact']
  ])('selects the registered renderer for %s artifacts', (artifactType, testId) => {
    const wrapper = mount(ArtifactRenderer, {
      props: { artifact: artifact({ artifact_type: artifactType }) },
      global: { stubs }
    })

    expect(wrapper.find(`[data-testid="${testId}"]`).exists()).toBe(true)
  })

  it.each([
    ['binding_pocket', 'pocket-result-artifact'],
    ['ligand_structure', 'ligand-structure-artifact'],
    ['molecule_table', 'file-artifact']
  ])('renders standard %s artifacts without falling back', (artifactType, testId) => {
    const wrapper = mount(ArtifactRenderer, {
      props: { artifact: artifact({ artifact_type: artifactType }) },
      global: { stubs }
    })

    expect(wrapper.find(`[data-testid="${testId}"]`).exists()).toBe(true)
    expect(wrapper.find('[data-testid="artifact-fallback"]').exists()).toBe(false)
  })

  it('uses a stable fallback for unknown artifact types', () => {
    const wrapper = mount(ArtifactRenderer, {
      props: { artifact: artifact({ artifact_type: 'unknown_result' }) },
      global: { stubs }
    })

    expect(wrapper.get('[data-testid="artifact-fallback"]').text()).toContain('unknown_result')
    expect(wrapper.text()).toContain('暂不支持')
  })

  it('renders ligand structures with the shared structure preview for renderable files', async () => {
    const wrapper = mount(ArtifactRenderer, {
      props: {
        artifact: artifact({
          artifact_type: 'ligand_structure',
          semantic_type: 'ligand_structure',
          name: 'ligand.sdf',
          latest_version: {
            ...version,
            filename: 'ligand.sdf',
            content_type: 'chemical/x-mdl-sdfile'
          }
        })
      },
      global: { stubs }
    })
    await flushPromises()

    expect(wrapper.find('[data-testid="ligand-structure-artifact"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="structure-artifact-preview"]').exists()).toBe(true)
  })

  it('prefers the ligand 3D role file when a ligand artifact exposes multiple role files', async () => {
    const twoDDownloadUrl =
      '/api/v1/artifacts/artifact-1/versions/version-1/files/structure_2d_sdf/download'
    const threeDDownloadUrl =
      '/api/v1/artifacts/artifact-1/versions/version-1/files/structure_3d_sdf/download'
    const wrapper = mount(ArtifactRenderer, {
      props: {
        artifact: artifact({
          artifact_type: 'ligand_structure',
          semantic_type: 'ligand_structure@1',
          name: 'aspirin',
          latest_version: {
            ...version,
            filename: 'ligand.sdf',
            content_type: 'chemical/x-mdl-sdfile',
            files: [
              {
                id: 'version-file-2d',
                role: 'structure_2d_sdf',
                file_id: 'file-2d',
                is_primary: false,
                sort_order: 1,
                filename: 'ligand.2d.sdf',
                content_type: 'chemical/x-mdl-sdfile',
                size_bytes: 512,
                sha256: 'b'.repeat(64),
                download_url: twoDDownloadUrl
              },
              {
                id: 'version-file-3d',
                role: 'structure_3d_sdf',
                file_id: 'file-3d',
                is_primary: false,
                sort_order: 2,
                filename: 'ligand.3d.sdf',
                content_type: 'chemical/x-mdl-sdfile',
                size_bytes: 1024,
                sha256: 'c'.repeat(64),
                download_url: threeDDownloadUrl
              }
            ]
          }
        })
      },
      global: { stubs }
    })
    await flushPromises()

    expect(wrapper.get('[data-testid="molecule-viewer"]').text()).toContain(
      '/files/structure_3d_sdf/download'
    )
  })

  it('prefers the prepared PDB role file when rendering prepared protein structures', async () => {
    const rawDownloadUrl =
      '/api/v1/artifacts/artifact-1/versions/version-1/files/raw_structure_file/download'
    const preparedDownloadUrl =
      '/api/v1/artifacts/artifact-1/versions/version-1/files/prepared_pdb/download'
    const wrapper = mount(ArtifactRenderer, {
      props: {
        artifact: artifact({
          artifact_type: 'protein_structure',
          semantic_type: 'protein_structure@1',
          name: 'prepared receptor',
          latest_version: {
            ...version,
            filename: 'raw.pdb',
            content_type: 'chemical/x-pdb',
            files: [
              {
                id: 'version-file-raw',
                role: 'raw_structure_file',
                file_id: 'file-raw',
                is_primary: true,
                sort_order: 1,
                filename: 'raw.pdb',
                content_type: 'chemical/x-pdb',
                size_bytes: 512,
                sha256: 'b'.repeat(64),
                download_url: rawDownloadUrl
              },
              {
                id: 'version-file-prepared',
                role: 'prepared_pdb',
                file_id: 'file-prepared',
                is_primary: false,
                sort_order: 2,
                filename: 'prepared.pdb',
                content_type: 'chemical/x-pdb',
                size_bytes: 1024,
                sha256: 'c'.repeat(64),
                download_url: preparedDownloadUrl
              }
            ]
          }
        })
      },
      global: { stubs }
    })
    await flushPromises()

    expect(wrapper.get('[data-testid="molecule-viewer"]').text()).toContain(
      '/files/prepared_pdb/download'
    )
  })

  it('exposes prepared protein role files as protected download links', () => {
    const wrapper = mount(ArtifactRenderer, {
      props: {
        artifact: artifact({
          artifact_type: 'protein_structure',
          semantic_type: 'protein_structure@1',
          latest_version: {
            ...version,
            filename: 'prepared.manifest.json',
            content_type: 'application/json',
            files: [
              {
                id: 'version-file-prepared',
                role: 'prepared_pdb',
                file_id: 'file-prepared',
                is_primary: true,
                sort_order: 1,
                filename: 'prepared.pdb',
                content_type: 'chemical/x-pdb',
                size_bytes: 1024,
                sha256: 'b'.repeat(64),
                download_url:
                  '/api/v1/artifacts/artifact-1/versions/version-1/files/prepared_pdb/download'
              },
              {
                id: 'version-file-pdbqt',
                role: 'receptor_pdbqt',
                file_id: 'file-pdbqt',
                is_primary: false,
                sort_order: 2,
                filename: 'receptor.pdbqt',
                content_type: 'chemical/x-pdbqt',
                size_bytes: 2048,
                sha256: 'c'.repeat(64),
                download_url:
                  '/api/v1/artifacts/artifact-1/versions/version-1/files/receptor_pdbqt/download'
              },
              {
                id: 'version-file-report',
                role: 'preparation_report_json',
                file_id: 'file-report',
                is_primary: false,
                sort_order: 3,
                filename: 'preparation_report.json',
                content_type: 'application/json',
                size_bytes: 512,
                sha256: 'd'.repeat(64),
                download_url:
                  '/api/v1/artifacts/artifact-1/versions/version-1/files/preparation_report_json/download'
              }
            ]
          }
        })
      },
      global: { stubs }
    })

    const pdbqt = wrapper.get('[data-testid="artifact-role-download-link:receptor_pdbqt"]')
    const report = wrapper.get('[data-testid="artifact-role-download-link:preparation_report_json"]')
    expect(pdbqt.attributes('href')).toContain('/files/receptor_pdbqt/download')
    expect(report.attributes('href')).toContain('/files/preparation_report_json/download')
    expect(wrapper.text()).toContain('receptor.pdbqt')
    expect(wrapper.text()).toContain('preparation_report.json')
  })

  it('builds file links through the protected artifact API instead of object storage URLs', () => {
    const wrapper = mount(ArtifactRenderer, {
      props: {
        artifact: {
          ...artifact({ artifact_type: 'file' }),
          object_storage_url: 'https://minio.internal/private-bucket/target.pdb'
        } as TypedArtifact
      },
      global: { stubs }
    })

    const link = wrapper.get('[data-testid="artifact-download-link"]')
    expect(link.attributes('href')).toBe('/api/v1/artifacts/artifact-1/versions/version-1/download')
    expect(link.attributes('href')).not.toContain('minio.internal')
  })

  it('shows delivery metadata from artifact version manifests', () => {
    const wrapper = mount(ArtifactRenderer, {
      props: {
        artifact: artifact({
          artifact_type: 'run_report',
          latest_version: {
            ...version,
            manifest_json: {
              type: 'run_report@1',
              metadata: {
                model_card_ref: 'example/MolP-PC/tool-package-v2/docs/model-card.md',
                verification_record_ref: 'example/MolP-PC/tool-package-v2/docs/verification-record.md',
                evidence_level: 'engineering_smoke_only'
              }
            }
          }
        })
      },
      global: { stubs }
    })

    const metadata = wrapper.get('[data-testid="artifact-delivery-metadata"]')
    expect(metadata.text()).toContain('交付元数据')
    expect(metadata.text()).toContain('example/MolP-PC/tool-package-v2/docs/model-card.md')
    expect(metadata.text()).toContain('example/MolP-PC/tool-package-v2/docs/verification-record.md')
    expect(metadata.text()).toContain('engineering_smoke_only')
  })

  it('renders artifact reference blocks in the conversation timeline with the shared renderer', () => {
    const message: ConversationMessage = {
      id: 'message-1',
      conversation_id: 'conversation-1',
      branch_id: 'branch-1',
      role: 'assistant',
      plain_text: '产物已生成',
      sequence: 1,
      content: [
        {
          type: 'artifact_ref',
          title: '口袋结果',
          artifact_id: 'artifact-1',
          artifact: artifact({ artifact_type: 'pocket_result', semantic_type: 'pocket_result' })
        }
      ]
    } as ConversationMessage

    const wrapper = mount(MessageTimeline, {
      props: { messages: [message], canRun: true },
      global: { stubs }
    })

    expect(wrapper.find('[data-testid="pocket-result-artifact"]').exists()).toBe(true)
  })

  it('prefers typed artifacts over legacy task output files in task visualization results', () => {
    const task = {
      id: 'task-1',
      tool_id: 'tool-1',
      status: 'success',
      progress: 100,
      created_at: '2026-07-30T00:00:00Z',
      artifacts: [artifact({ artifact_type: 'run_report', name: '运行报告' })],
      output_files: []
    } as unknown as Task

    const wrapper = mount(ResultVisualizationPanel, {
      props: { task },
      global: { stubs }
    })

    expect(wrapper.find('[data-testid="run-report-artifact"]').exists()).toBe(true)
  })
})
