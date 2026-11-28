import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import MdResult from './MdResult.vue'
import { getArtifactDetail, getMdResult } from '@/api/md'
import { getTaskDetail } from '@/api/tasks'
import { openTaskEventStream } from '@/api/task-events'
import { fetchProtectedFileText, triggerProtectedFileDownload } from '@/utils/protected-file-access'
import type { TypedArtifact } from '@/types/artifacts'
import type { MdResultDetail } from '@/types/md'
import { buildContactRows, downsampleSeries } from './analysis'

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { id: 'task-1' }, fullPath: '/md/task-1/result' }),
  useRouter: () => ({ push: vi.fn() }),
}))

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (key: string) => key }),
}))

vi.mock('ant-design-vue', () => ({
  message: { error: vi.fn() },
}))

vi.mock('@/api/md', async importOriginal => {
  const actual = await importOriginal<typeof import('@/api/md')>()
  return {
    ...actual,
    getMdResult: vi.fn(),
    getArtifactDetail: vi.fn(),
  }
})

vi.mock('@/api/tasks', () => ({
  getTaskDetail: vi.fn(),
}))

vi.mock('@/api/task-events', () => ({
  openTaskEventStream: vi.fn(() => ({ available: false, close: vi.fn() })),
}))

vi.mock('@/utils/protected-file-access', () => ({
  fetchProtectedFileText: vi.fn(async (url: string) =>
    url.includes('metadata') ? JSON.stringify({ movie_time_ps: [0, 2, 4] }) : ''),
  triggerProtectedFileDownload: vi.fn(async () => undefined),
}))

const stubs = {
  'app-page-header': true,
  'task-context-bar': true,
  'skeleton-detail': true,
  'app-description-list': true,
  'md-echart': true,
  'result-disclaimer': true,
  'structure-artifact-preview': {
    name: 'StructureArtifactPreview',
    props: ['artifact', 'preferredFileRoles', 'frameTimesPs', 'canExportMovie'],
    emits: ['export-movie', 'movie-unavailable', 'movie-available'],
    template:
      '<div data-testid="structure-preview-stub" :data-can-export="canExportMovie" :data-frame-times="JSON.stringify(frameTimesPs)" :data-roles="JSON.stringify(preferredFileRoles)" @click="$emit(\'export-movie\')"><button data-testid="fail-movie" @click.stop="$emit(\'movie-unavailable\', { artifactId: \'artifact-1\', versionId: \'version-1\' })">fail</button><button data-testid="recover-movie" @click.stop="$emit(\'movie-available\', { artifactId: \'artifact-1\', versionId: \'version-1\' })">recover</button></div>',
  },
  'a-card': { template: '<div><slot /></div>' },
  'a-row': { template: '<div><slot /></div>' },
  'a-col': { template: '<div><slot /></div>' },
  'a-space': { template: '<div><slot /></div>' },
  'a-button': {
    props: ['disabled', 'loading', 'block'],
    template: '<button :disabled="disabled" @click="$emit(\'click\')"><slot /></button>',
  },
  'a-alert': {
    props: ['type', 'message', 'showIcon'],
    template: '<div class="a-alert" :data-type="type" :data-message="message" />',
  },
  'a-empty': true,
  'a-progress': true,
  'a-tag': { template: '<span><slot /></span>' },
  'a-table': true,
  'a-result': { template: '<div><slot /><slot name="extra" /></div>' },
}

function makeArtifact(roles: string[]): TypedArtifact {
  return {
    id: 'artifact-1',
    project_id: 'project-1',
    artifact_type: 'md_trajectory',
    semantic_type: 'md_trajectory',
    name: 'md_trajectory',
    latest_version: {
      id: 'version-1',
      version: 1,
      filename: 'md_trajectory.pdb',
      size_bytes: 1024,
      sha256: 'a'.repeat(64),
      status: 'available',
      created_at: '2026-11-23T00:00:00Z',
      files: roles.map((role, index) => ({
        id: `file-${role}`,
        role,
        file_id: `file-${role}`,
        is_primary: index === 0,
        sort_order: index,
        filename: `${role}.pdb`,
        download_url: `/api/v1/files/${role}/download`,
      })),
    },
    created_at: '2026-11-23T00:00:00Z',
    updated_at: '2026-11-23T00:00:00Z',
  }
}

async function mountWithFiles(roles: string[]) {
  vi.mocked(getMdResult).mockResolvedValue({
    status: 'success',
    outputs: [{ id: 'artifact-1', standard_type: 'md_trajectory@1' }],
  } as unknown as MdResultDetail)
  vi.mocked(getTaskDetail).mockResolvedValue({
    data: { id: 'task-1', status: 'success', progress: 100 },
  } as unknown as Awaited<ReturnType<typeof getTaskDetail>>)
  vi.mocked(getArtifactDetail).mockResolvedValue(makeArtifact(roles))

  const wrapper = mount(MdResult, { global: { stubs } })
  await flushPromises()
  await flushPromises()
  return wrapper
}

describe('MD result movie integration', () => {
  // 用 reset 而非 clear：`clearAllMocks` 不会恢复被上一条用例覆盖的 mock 实现，
  // 会让「只有 movie」的用例继承上一条「metadata 为空」的行为，产生顺序依赖。
  beforeEach(() => {
    vi.resetAllMocks()
    vi.mocked(fetchProtectedFileText).mockImplementation(async (url: string) =>
      url.includes('metadata') ? JSON.stringify({ movie_time_ps: [0, 2, 4] }) : '',
    )
    vi.mocked(openTaskEventStream).mockReturnValue({ available: false, close: vi.fn() })
  })

  it('offers movie download and playable preview when trajectory_movie_pdb exists', async () => {
    const wrapper = await mountWithFiles(['trajectory_movie_pdb', 'topology_pdb', 'metadata_json'])

    expect(wrapper.get('[data-testid="md-download-movie"]').attributes('disabled')).toBeUndefined()

    const alerts = wrapper.findAll('.a-alert')
    const movieAlert = alerts.find(alert => alert.attributes('data-message') === 'md.result.movieNotice')
    expect(movieAlert).toBeTruthy()
    expect(movieAlert?.attributes('data-type')).toBe('info')

    const preview = wrapper.get('[data-testid="structure-preview-stub"]')
    expect(preview.attributes('data-can-export')).toBe('true')
    expect(preview.attributes('data-frame-times')).toBe('[0,2,4]')
    expect(preview.attributes('data-roles')).toBe('["trajectory_movie_pdb","topology_pdb"]')

    await preview.trigger('click')
    expect(triggerProtectedFileDownload).toHaveBeenCalledWith(
      {
        url: '/api/v1/files/trajectory_movie_pdb/download',
        filename: 'trajectory_movie_pdb.pdb',
      },
      {},
      { requireContent: true },
    )
  })

  it('falls back to the topology preview when the movie fails to load', async () => {
    const wrapper = await mountWithFiles(['trajectory_movie_pdb', 'topology_pdb', 'metadata_json'])
    await wrapper.get('[data-testid="fail-movie"]').trigger('click')
    await flushPromises()

    const alerts = wrapper.findAll('.a-alert')
    const fallbackAlert = alerts.find(
      alert => alert.attributes('data-message') === 'md.result.movieFallbackNotice',
    )
    expect(fallbackAlert).toBeTruthy()
    expect(fallbackAlert?.attributes('data-type')).toBe('warning')
    expect(
      alerts.some(alert => alert.attributes('data-message') === 'md.result.movieNotice'),
    ).toBe(false)

    const preview = wrapper.get('[data-testid="structure-preview-stub"]')
    expect(preview.attributes('data-frame-times')).toBe('null')
    expect(preview.attributes('data-can-export')).toBe('false')
    expect(wrapper.get('.md-result__viewer-note').text()).toBe('md.result.staticPreviewNote')
  })

  it('clears the movie fallback when the preview reports the same version available again', async () => {
    const wrapper = await mountWithFiles([
      'trajectory_movie_pdb',
      'topology_pdb',
      'metadata_json',
    ])
    await wrapper.get('[data-testid="fail-movie"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-testid="structure-preview-stub"]').attributes('data-can-export')).toBe(
      'false',
    )

    // 同一版本重新拉取后影片恢复：预览重新选中影片并上报 available，页面必须解除降级。
    await wrapper.get('[data-testid="recover-movie"]').trigger('click')
    await flushPromises()

    const preview = wrapper.get('[data-testid="structure-preview-stub"]')
    expect(preview.attributes('data-can-export')).toBe('true')
    expect(preview.attributes('data-frame-times')).toBe('[0,2,4]')
    expect(wrapper.get('.md-result__viewer-note').text()).toBe('md.result.moviePreviewNote')
    expect(
      wrapper
        .findAll('.a-alert')
        .some(alert => alert.attributes('data-message') === 'md.result.movieFallbackNotice'),
    ).toBe(false)
  })

  it('ignores a late movie failure reported for a version that is no longer current', async () => {
    type StreamHandlers = Parameters<typeof openTaskEventStream>[1]
    let streamHandlers: Partial<StreamHandlers> = {}
    vi.mocked(openTaskEventStream).mockImplementation((_id, handlers) => {
      streamHandlers = handlers
      return { available: true, close: vi.fn() }
    })
    vi.mocked(getMdResult).mockResolvedValue({
      status: 'running',
      outputs: [{ id: 'artifact-1', standard_type: 'md_trajectory@1' }],
    } as unknown as MdResultDetail)
    vi.mocked(getTaskDetail).mockResolvedValue({
      data: { id: 'task-1', status: 'running', progress: 50 },
    } as unknown as Awaited<ReturnType<typeof getTaskDetail>>)
    vi.mocked(getArtifactDetail).mockResolvedValue(
      makeArtifact(['trajectory_movie_pdb', 'topology_pdb', 'metadata_json']),
    )

    const wrapper = mount(MdResult, { global: { stubs } })
    await flushPromises()
    await flushPromises()

    const refreshed = makeArtifact(['trajectory_movie_pdb', 'topology_pdb', 'metadata_json'])
    refreshed.latest_version = { ...refreshed.latest_version, id: 'version-2', version: 2 }
    vi.mocked(getArtifactDetail).mockResolvedValue(refreshed)
    streamHandlers.onDone?.({} as never)
    await flushPromises()
    await flushPromises()
    expect(wrapper.get('[data-testid="structure-preview-stub"]').attributes('data-can-export')).toBe(
      'true',
    )

    // 旧版本（version-1）那次加载的失败事件迟到，不能把 version-2 的影片重新锁死。
    await wrapper.get('[data-testid="fail-movie"]').trigger('click')
    await flushPromises()

    const preview = wrapper.get('[data-testid="structure-preview-stub"]')
    expect(preview.attributes('data-can-export')).toBe('true')
    expect(preview.attributes('data-frame-times')).toBe('[0,2,4]')
    expect(
      wrapper
        .findAll('.a-alert')
        .some(alert => alert.attributes('data-message') === 'md.result.movieFallbackNotice'),
    ).toBe(false)
  })

  it('re-enables playback and export when the same artifact publishes a healthy new version', async () => {
    type StreamHandlers = Parameters<typeof openTaskEventStream>[1]
    let streamHandlers: Partial<StreamHandlers> = {}
    vi.mocked(openTaskEventStream).mockImplementation((_id, handlers) => {
      streamHandlers = handlers
      return { available: true, close: vi.fn() }
    })
    vi.mocked(getMdResult).mockResolvedValue({
      status: 'running',
      outputs: [{ id: 'artifact-1', standard_type: 'md_trajectory@1' }],
    } as unknown as MdResultDetail)
    vi.mocked(getTaskDetail).mockResolvedValue({
      data: { id: 'task-1', status: 'running', progress: 50 },
    } as unknown as Awaited<ReturnType<typeof getTaskDetail>>)
    vi.mocked(getArtifactDetail).mockResolvedValue(
      makeArtifact(['trajectory_movie_pdb', 'topology_pdb', 'metadata_json']),
    )

    const wrapper = mount(MdResult, { global: { stubs } })
    await flushPromises()
    await flushPromises()

    await wrapper.get('[data-testid="fail-movie"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-testid="structure-preview-stub"]').attributes('data-can-export')).toBe('false')
    expect(wrapper.get('[data-testid="structure-preview-stub"]').attributes('data-frame-times')).toBe('null')

    // 同一 artifact 刷新出新版本：旧的失败标记必须清掉，否则新影片仍然不能播放/导出。
    const refreshed = makeArtifact(['trajectory_movie_pdb', 'topology_pdb', 'metadata_json'])
    refreshed.latest_version = { ...refreshed.latest_version, id: 'version-2', version: 2 }
    vi.mocked(getArtifactDetail).mockResolvedValue(refreshed)
    streamHandlers.onDone?.({} as never)
    await flushPromises()
    await flushPromises()

    const preview = wrapper.get('[data-testid="structure-preview-stub"]')
    expect(preview.attributes('data-can-export')).toBe('true')
    expect(preview.attributes('data-frame-times')).toBe('[0,2,4]')
    expect(
      wrapper.findAll('.a-alert').some(
        alert => alert.attributes('data-message') === 'md.result.movieFallbackNotice',
      ),
    ).toBe(false)
    expect(wrapper.get('.md-result__viewer-note').text()).toBe('md.result.moviePreviewNote')
  })

  it('degrades legacy tasks without a movie to a static topology preview', async () => {
    vi.mocked(fetchProtectedFileText).mockResolvedValue(JSON.stringify({}))
    const wrapper = await mountWithFiles(['topology_pdb', 'metadata_json'])

    expect(wrapper.get('[data-testid="md-download-movie"]').attributes('disabled')).toBeDefined()

    const alerts = wrapper.findAll('.a-alert')
    const trajectoryAlert = alerts.find(alert => alert.attributes('data-message') === 'md.result.trajectoryNotice')
    expect(trajectoryAlert).toBeTruthy()
    expect(trajectoryAlert?.attributes('data-type')).toBe('warning')
    expect(alerts.some(alert => alert.attributes('data-message') === 'md.result.movieNotice')).toBe(false)

    const preview = wrapper.get('[data-testid="structure-preview-stub"]')
    expect(preview.attributes('data-can-export')).toBe('false')
    expect(preview.attributes('data-frame-times')).toBe('null')
  })

  it('keeps the 3D preview card and movie notice populated when only trajectory_movie_pdb exists', async () => {
    // 无 topology_pdb 的历史兼容场景：只靠多帧 movie 也必须有可播放预览，不能变成空卡片。
    const wrapper = await mountWithFiles(['trajectory_movie_pdb', 'metadata_json'])

    expect(wrapper.get('[data-testid="md-download-movie"]').attributes('disabled')).toBeUndefined()

    // 提示切换只取决于 movie 是否存在，与 topology_pdb 无关。
    const alerts = wrapper.findAll('.a-alert')
    expect(alerts.some(alert => alert.attributes('data-message') === 'md.result.movieNotice')).toBe(true)
    expect(alerts.some(alert => alert.attributes('data-message') === 'md.result.trajectoryNotice')).toBe(false)
    expect(alerts.some(alert => alert.attributes('data-message') === 'md.result.noTrajectoryArtifact')).toBe(false)

    const preview = wrapper.get('[data-testid="structure-preview-stub"]')
    expect(preview.attributes('data-can-export')).toBe('true')
    expect(preview.attributes('data-frame-times')).toBe('[0,2,4]')
    expect(preview.attributes('data-roles')).toBe('["trajectory_movie_pdb","topology_pdb"]')
    // `get` 命中结构预览桩即可证明：没有 topology_pdb 时预览卡片未被空状态替换。
  })

  it('renders no top-level missing-trajectory notice while a movie exists', async () => {
    const wrapper = await mountWithFiles(['trajectory_movie_pdb', 'topology_pdb', 'metadata_json'])
    expect(
      wrapper
        .findAll('.a-alert')
        .some(alert => alert.attributes('data-message') === 'md.result.noTrajectoryArtifact'),
    ).toBe(false)
    expect(fetchProtectedFileText).toHaveBeenCalledWith('/api/v1/files/metadata_json/download')
  })
})

describe('MD result chart sampling', () => {
  it('preserves extrema while limiting display samples', () => {
    const rows = Array.from({ length: 2000 }, (_, index) => ({ time_ps: index, rmsd_nm: index === 1001 ? 99 : 1 }))
    const sampled = downsampleSeries(rows, 100, row => row.rmsd_nm)
    expect(sampled.length).toBeLessThanOrEqual(100)
    expect(sampled[0]?.time_ps).toBe(0)
    expect(sampled[sampled.length - 1]?.time_ps).toBe(1999)
    expect(sampled.some(row => row.rmsd_nm === 99)).toBe(true)
  })

  it('parses contacts_csv rows cleanly', () => {
    const contacts = buildContactRows([
      {
        residue_chain: 'A',
        residue_seq: '3',
        residue_icode: '',
        residue_name: 'SER',
        interaction_type: 'hbond_acceptor',
        occupancy: '1.0000',
        contact_frames: '2',
        total_frames: '2',
        min_distance_nm: '0.2783',
        mean_distance_nm: '0.2881'
      },
      { residue_seq: 'invalid', interaction_type: 'vdw_contact' }
    ])
    expect(contacts).toHaveLength(1)
    expect(contacts[0]).toMatchObject({
      residue_chain: 'A',
      residue_seq: 3,
      residue_name: 'SER',
      interaction_type: 'hbond_acceptor',
      occupancy: 1,
      min_distance_nm: 0.2783
    })
  })
})