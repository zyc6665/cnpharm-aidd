import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import BoardView from './Board.vue'
import BoardList from './List.vue'
import { getProjectArtifacts } from '@/api/artifacts'
import { getResearchBoard, getResearchBoards } from '@/api/research-boards'

const push = vi.fn()

vi.mock('vue-router', async importOriginal => {
  const actual = await importOriginal<typeof import('vue-router')>()
  return {
    ...actual,
    useRoute: () => ({ params: { projectId: 'project-1', boardId: 'board-1' } }),
    useRouter: () => ({ push }),
  }
})

vi.mock('@/api/research-boards', () => ({
  createBoardWorkflowDraft: vi.fn(),
  createResearchBoard: vi.fn(),
  deleteResearchBoard: vi.fn(),
  getResearchBoard: vi.fn(),
  getResearchBoards: vi.fn(),
  updateResearchBoard: vi.fn(),
}))

vi.mock('@/api/files', () => ({
  getFileList: vi.fn().mockResolvedValue({ data: { items: [] } }),
}))

vi.mock('@/api/artifacts', () => ({
  buildArtifactVersionDownloadUrl: (artifactId: string, versionId: string) =>
    `/api/v1/artifacts/${artifactId}/versions/${versionId}/download`,
  getProjectArtifacts: vi.fn(),
}))

vi.mock('@/stores', () => ({
  useToolsStore: () => ({ workflowToolOptions: [], fetchWorkflowTools: vi.fn() }),
}))

const board = {
  id: 'board-1',
  project_id: 'project-1',
  owner_id: 'owner-1',
  name: '口袋假设白板',
  description: '整理蛋白口袋证据',
  content: {
    nodes: [
      {
        id: 'artifact-1',
        type: 'artifact',
        position: { x: 0, y: 0 },
        artifact_id: 'artifact-1',
      },
      ...Array.from({ length: 199 }, (_, index) => ({
        id: `note-${index}`,
        type: 'note',
        position: { x: ((index + 1) % 10) * 120, y: Math.floor((index + 1) / 10) * 80 },
        content: `假设 ${index}`,
      })),
    ],
    edges: [],
    viewport: { x: 0, y: 0, zoom: 1 },
  },
  version: 1,
  created_at: '2026-07-30T00:00:00Z',
  updated_at: '2026-07-30T01:00:00Z',
}

const stubs = {
  'a-button': {
    emits: ['click'],
    template: '<button v-bind="$attrs" @click="$emit(\'click\')"><slot /></button>',
  },
  AButton: {
    template: '<button v-bind="$attrs" @click="$attrs.onClick && $attrs.onClick($event)"><slot /></button>',
  },
  AInput: { template: '<input />' },
  ATextarea: { template: '<textarea />' },
  ASelect: { template: '<select />' },
  ASpace: { template: '<div><slot /></div>' },
  ASpin: { template: '<div><slot /></div>' },
  AAlert: { template: '<div><slot /></div>' },
  ADescriptions: { template: '<dl><slot /></dl>' },
  ADescriptionsItem: { template: '<div><slot /></div>' },
  AEmpty: true,
  ASkeleton: true,
  APopconfirm: { template: '<div><slot /></div>' },
  ATag: { template: '<span><slot /></span>' },
  DeleteOutlined: true,
  ExpandOutlined: true,
  FullscreenExitOutlined: true,
  LinkOutlined: true,
  PlusOutlined: true,
  RedoOutlined: true,
  SaveOutlined: true,
  UndoOutlined: true,
  ZoomInOutlined: true,
  ZoomOutOutlined: true,
}

describe('project research board page', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(getResearchBoard).mockResolvedValue({ data: board } as never)
    vi.mocked(getProjectArtifacts).mockResolvedValue({
      data: {
        items: [{
          id: 'artifact-1',
          project_id: 'project-1',
          artifact_type: 'file',
          semantic_type: 'run_report',
          name: '口袋结果',
          latest_version: {
            id: 'version-1',
            version: 1,
            filename: 'pocket.json',
            content_type: 'application/json',
            size_bytes: 512,
            sha256: 'a'.repeat(64),
            status: 'available',
            created_at: '2026-07-30T00:00:00Z',
          },
          created_at: '2026-07-30T00:00:00Z',
          updated_at: '2026-07-30T00:00:00Z',
        }],
      },
    } as never)
    vi.mocked(getResearchBoards).mockResolvedValue({
      data: { items: [{ ...board, node_count: 200 }], total: 1, page: 1, page_size: 100 },
    } as never)
  })

  it('renders a full-page canvas with object palette, inspector, and focus mode', async () => {
    const wrapper = mount(BoardView, { global: { stubs } })
    await flushPromises()

    expect(wrapper.find('[data-testid="research-board-page"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="board-canvas"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="board-object-palette"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="board-inspector"]').exists()).toBe(true)
    expect(wrapper.find('.ant-drawer').exists()).toBe(false)
    expect(wrapper.find('.ant-modal').exists()).toBe(false)
    expect(wrapper.find('[data-testid="file-artifact"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="board-stage"]').attributes('style')).toContain('width: 1600px')
    expect(wrapper.get('[data-testid="board-stage"]').attributes('style')).toContain('height: 1000px')

    await wrapper.get('[data-testid="toggle-focus-mode"]').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="board-object-palette"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="board-inspector"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="research-board-page"]').classes()).toContain('is-focused')
  })

  it('opens a project board from the compatibility list using the project route', async () => {
    const wrapper = mount(BoardList, { global: { stubs } })
    await flushPromises()

    await wrapper.get('[data-testid="open-board-board-1"]').trigger('click')
    expect(push).toHaveBeenCalledWith('/projects/project-1/boards/board-1')
  })
})
