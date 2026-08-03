import { mount } from '@vue/test-utils'
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
    ['ligand_structure', 'pocket-result-artifact'],
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
