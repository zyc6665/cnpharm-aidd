import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import MoleculeViewer from './MoleculeViewer.vue'
import { computeFrameIntervalMs, type VisualizationScene } from '@/domain/tasks'

function deferred<T = undefined>() {
  let resolve!: (value?: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = (value?: T) => res(value as T)
    reject = rej
  })
  return { promise, resolve, reject }
}

interface MockPreset {
  structure: { ref: string }
  model?: { ref: string }
  /** Mol* 5.9 `applyPreset` 返回 `representation.representations` 这层。 */
  representation?: { representations?: Record<string, { ref: string }> }
}

interface MockHierarchyRepresentation {
  cell: { transform: { ref: string } }
}

interface MockHierarchyComponent {
  ref: string
  representations?: MockHierarchyRepresentation[]
}

interface MockHierarchyStructure {
  cell: { transform: { ref: string }; obj?: { data?: { id?: string } } }
  components: MockHierarchyComponent[]
}

function defaultHierarchy(): MockHierarchyStructure[] {
  return [
    {
      cell: { transform: { ref: 'structure-ref-1' }, obj: { data: { id: 'mock-structure' } } },
      components: [{ ref: 'comp-1' }],
    },
  ]
}

/** 模拟样式切换后状态树里的 representation 节点（真实 Mol* 会清空并重建它们）。 */
function setLiveRepresentations(structureRefKey: string, refs: string[]): void {
  const structure = mockState.hierarchyStructures.find(
    entry => entry.cell.transform.ref === structureRefKey,
  )
  if (!structure) return
  structure.components = [
    {
      ref: 'comp-live',
      representations: refs.map(ref => ({ cell: { transform: { ref } } })),
    },
  ]
}

function defaultPreset(): MockPreset {
  return { structure: { ref: 'structure-ref-1' }, model: { ref: 'model-ref-1' } }
}

const mockState = {
  applyPreset: vi.fn(async () => mockState.presetQueue.shift() ?? defaultPreset()),
  componentApplyPreset: vi.fn(async () => undefined),
  componentClear: vi.fn(async () => undefined),
  updateRepresentationsTheme: vi.fn(async () => undefined),
  tryCreateComponentFromExpression: vi.fn(async () => ({ ref: 'comp-ref-1' })),
  addRepresentation: vi.fn(async () => undefined),
  setBackground: vi.fn((_viewer?: unknown, _bg?: unknown) => undefined),
  downloadScreenshot: vi.fn(async (_viewer?: unknown, _filename?: unknown) => true),
  resetCamera: vi.fn(),
  focusSphere: vi.fn(),
  setSnapshot: vi.fn(),
  disposeViewer: vi.fn(),
  updateModel: vi.fn(),
  /** 记录每次 `state.build().to(ref).update(payload)` 的 (ref, payload)，用于多条目同步断言。 */
  updateCalls: [] as Array<{ ref: string; payload: { modelIndex: number } }>,
  /** 模拟 Mol* 状态树 cell 状态；真实 Mol* 在 Update resolve 后仍可能把目标 cell 置为 error。 */
  cells: new Map<string, { status?: string }>(),
  stateUpdate: vi.fn(async (_viewer?: unknown, _opts?: unknown) => undefined),
  /** 由测试按需设置：parseTrajectory 逐次返回的 `trajectory.obj.data.frameCount`。 */
  frameCountQueue: [] as number[],
  /** 由测试按需设置：applyPreset 逐次返回的 structure/model ref（缺省共用 structure-ref-1）。 */
  presetQueue: [] as MockPreset[],
  /** 缺省帧数（未配置队列时使用）。 */
  trajectoryFrameCount: 1,
  /** 当前状态树层级；样式切换用例会按需替换 representation 节点。 */
  hierarchyStructures: defaultHierarchy(),
  extractedChains: [
    {
      chain: 'A',
      residues: [
        { key: 'A:1', chain: 'A', seqId: 1, compId: 'MET', oneLetter: 'M' },
        { key: 'A:2', chain: 'A', seqId: 2, compId: 'ALA', oneLetter: 'A' },
      ],
    },
  ],
}

vi.mock('vue-i18n', () => ({
  useI18n: () => ({
    t: (key: string, params?: Record<string, unknown>) =>
      params?.count !== undefined ? `${key}:${params.count}` : key,
  }),
}))

vi.mock('ant-design-vue', () => ({
  message: {
    success: vi.fn(),
    warning: vi.fn(),
  },
}))

vi.mock('molstar/lib/mol-plugin/commands', async importOriginal => {
  const actual = await importOriginal<typeof import('molstar/lib/mol-plugin/commands')>()
  return {
    ...actual,
    PluginCommands: {
      ...actual.PluginCommands,
      State: {
        ...actual.PluginCommands.State,
        Update: (viewer: unknown, opts: unknown) => mockState.stateUpdate(viewer, opts),
      },
    },
  }
})

vi.mock('@/utils/protected-file-access', () => ({
  createProtectedObjectUrl: vi.fn(async (url: string) => ({
    url: `blob:${url}`,
    revoke: vi.fn(),
  })),
}))

vi.mock('./molstar-viewer-kernel', () => ({
  createMolstarViewer: vi.fn(async () => ({
    handleResize: vi.fn(),
    dispose: mockState.disposeViewer,
    plugin: {
      clear: vi.fn(async () => undefined),
      canvas3d: {
        camera: {
          getSnapshot: () => ({ position: [0, 0, 10] }),
        },
        setProps: vi.fn(),
      },
      layout: {
        state: { expandToFullscreen: false, isExpanded: false },
        events: {
          updated: { subscribe: () => ({ unsubscribe: vi.fn() }) },
        },
      },
      behaviors: {
        interaction: {
          click: { subscribe: () => ({ unsubscribe: vi.fn() }) },
        },
      },
      state: {
        data: {
          cells: mockState.cells,
          build: () => ({
            delete: vi.fn(),
            commit: vi.fn(async () => undefined),
            to: vi.fn((ref: string) => ({
              update: (payload: { modelIndex: number }) => {
                mockState.updateCalls.push({ ref, payload })
                mockState.updateModel(payload)
              },
            })),
          }),
        },
      },
      builders: {
        data: {
          download: vi.fn(async () => ({ ref: 'data-ref' })),
        },
        structure: {
          parseTrajectory: vi.fn(async () => ({
            ref: 'traj-ref',
            obj: { data: { frameCount: mockState.frameCountQueue.shift() ?? mockState.trajectoryFrameCount } },
          })),
          hierarchy: {
            applyPreset: mockState.applyPreset,
          },
          tryCreateComponentFromExpression: mockState.tryCreateComponentFromExpression,
          representation: {
            addRepresentation: mockState.addRepresentation,
          },
        },
      },
      managers: {
        camera: {
          reset: mockState.resetCamera,
          focusSphere: mockState.focusSphere,
          setSnapshot: mockState.setSnapshot,
        },
        structure: {
          hierarchy: {
            current: {
              structures: mockState.hierarchyStructures,
            },
          },
          component: {
            applyPreset: mockState.componentApplyPreset,
            clear: mockState.componentClear,
            updateRepresentationsTheme: mockState.updateRepresentationsTheme,
          },
        },
      },
    },
  })),
  createRevocableResourceRegistry: () => {
    const revokers: Array<() => void> = []
    return {
      add: (fn: () => void) => revokers.push(fn),
      clear: () => {
        revokers.forEach(fn => fn())
        revokers.length = 0
      },
    }
  },
  disposeMolstarViewer: (viewer: { dispose?: () => void } | null) => viewer?.dispose?.(),
  setMolstarBackgroundColor: (viewer: unknown, bg: unknown) => mockState.setBackground(viewer, bg),
  downloadMolstarScreenshot: (viewer: unknown, filename?: unknown) => mockState.downloadScreenshot(viewer, filename),
}))

vi.mock('@/domain/tasks', async importOriginal => {
  const actual = await importOriginal<typeof import('@/domain/tasks')>()
  return {
    ...actual,
    createNormalizedSdfObjectUrl: vi.fn(async (url: string) => ({
      url: `blob:normalized:${url}`,
      revoke: vi.fn(),
    })),
    extractPolymerSequenceFromStructure: () => mockState.extractedChains,
  }
})

function buildProteinScene(): VisualizationScene {
  return {
    entries: [
      {
        key: 'protein-1',
        url: '/api/v1/files/p1/download',
        label: 'target.pdb',
        source: 'output',
        role: 'receptor',
        format: 'pdb',
        extension: '.pdb',
      },
    ],
    inputEntries: [],
    outputEntries: [],
    supportedOutputFiles: [],
    unsupportedOutputFiles: [],
    hasRenderableOutput: true,
    selectedOutputKey: 'protein-1',
  }
}

function buildMovieScene(options: { preferComplexRepresentation?: boolean } = {}): VisualizationScene {
  return {
    entries: [
      {
        key: 'movie-1',
        url: '/api/v1/files/movie/download',
        label: 'trajectory_movie.pdb',
        source: 'output',
        role: 'structure',
        format: 'pdb',
        extension: '.pdb',
        ...(options.preferComplexRepresentation ? { preferComplexRepresentation: true } : {}),
      },
    ],
    inputEntries: [],
    outputEntries: [],
    supportedOutputFiles: [],
    unsupportedOutputFiles: [],
    hasRenderableOutput: true,
    selectedOutputKey: 'movie-1',
  }
}

function buildMultiMovieScene(): VisualizationScene {
  return {
    entries: [
      {
        key: 'receptor-1',
        url: '/api/v1/files/receptor-movie/download',
        label: 'receptor_movie.pdb',
        source: 'input',
        role: 'receptor',
        format: 'pdb',
        extension: '.pdb',
      },
      {
        key: 'movie-2',
        url: '/api/v1/files/movie-2/download',
        label: 'trajectory_movie.pdb',
        source: 'output',
        role: 'structure',
        format: 'pdb',
        extension: '.pdb',
        preferComplexRepresentation: true,
      },
      {
        key: 'movie-3',
        url: '/api/v1/files/movie-3/download',
        label: 'secondary_movie.pdb',
        source: 'output',
        role: 'structure',
        format: 'pdb',
        extension: '.pdb',
      },
    ],
    inputEntries: [],
    outputEntries: [],
    supportedOutputFiles: [],
    unsupportedOutputFiles: [],
    hasRenderableOutput: true,
    selectedOutputKey: 'movie-2',
  }
}

function buildFallbackScene(): VisualizationScene {
  return {
    entries: [
      {
        key: 'movie-1',
        url: '/api/v1/files/movie/download',
        label: 'trajectory_movie.pdb',
        source: 'output',
        role: 'structure',
        format: 'pdb',
        extension: '.pdb',
        fallbackOnFailure: true,
      },
      {
        key: 'topology-1',
        url: '/api/v1/files/topology/download',
        label: 'topology.pdb',
        source: 'output',
        role: 'structure',
        format: 'pdb',
        extension: '.pdb',
      },
    ],
    inputEntries: [],
    outputEntries: [],
    supportedOutputFiles: [],
    unsupportedOutputFiles: [],
    hasRenderableOutput: true,
    selectedOutputKey: 'movie-1',
  }
}

function buildDockingScene(): VisualizationScene {
  return {
    entries: [
      {
        key: 'receptor-1',
        url: '/api/v1/files/receptor/download',
        label: 'receptor.pdb',
        source: 'input',
        role: 'receptor',
        format: 'pdb',
        extension: '.pdb',
      },
      {
        key: 'ligand-1',
        url: '/api/v1/files/pose1/download',
        label: 'pose_1.sdf',
        source: 'output',
        role: 'ligand',
        format: 'sdf',
        extension: '.sdf',
      },
    ],
    inputEntries: [],
    outputEntries: [],
    supportedOutputFiles: [],
    unsupportedOutputFiles: [],
    hasRenderableOutput: true,
    selectedOutputKey: 'ligand-1',
  }
}

describe('MoleculeViewer', () => {
  afterEach(() => {
    vi.useRealTimers()
  })
  beforeEach(() => {
    vi.clearAllMocks()
    mockState.trajectoryFrameCount = 1
    mockState.frameCountQueue = []
    mockState.presetQueue = []
    mockState.updateCalls = []
    mockState.cells.clear()
    mockState.hierarchyStructures = defaultHierarchy()
    mockState.stateUpdate.mockReset()
    mockState.stateUpdate.mockImplementation(async () => undefined)
    mockState.extractedChains = [
      {
        chain: 'A',
        residues: [
          { key: 'A:1', chain: 'A', seqId: 1, compId: 'MET', oneLetter: 'M' },
          { key: 'A:2', chain: 'A', seqId: 2, compId: 'ALA', oneLetter: 'A' },
        ],
      },
    ]
  })

  it('keeps compact variant minimal without PyMOL controls or sequence bar', async () => {
    const wrapper = mount(MoleculeViewer, {
      props: {
        scene: buildProteinScene(),
        mode: 'protein',
        variant: 'compact',
      },
      global: {
        stubs: {
          ASpin: true,
          AAlert: true,
        },
      },
    })

    await flushPromises()

    expect(wrapper.find('.viewer-mode').text()).toBe('tasks.visualizationModes.protein')
    expect(wrapper.find('[data-testid="viewer-reset"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="viewer-representation-select"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="viewer-sequence-bar"]').exists()).toBe(false)
  })

  it('renders full PyMOL-like toolbar and sequence bar, and updates without re-downloading', async () => {
    const wrapper = mount(MoleculeViewer, {
      props: {
        scene: buildProteinScene(),
        mode: 'protein',
        variant: 'full',
      },
      global: {
        stubs: {
          ASpin: true,
          AAlert: true,
        },
      },
    })

    await flushPromises()

    expect(wrapper.find('.viewer-mode').text()).toBe('tasks.visualizationModes.protein')
    expect(wrapper.find('[data-testid="viewer-representation-select"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="viewer-color-select"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="viewer-sequence-bar"]').exists()).toBe(true)

    const initialLoadCalls = mockState.applyPreset.mock.calls.length

    await wrapper.get('[data-testid="viewer-representation-select"]').setValue('surface')
    await flushPromises()
    expect(mockState.componentApplyPreset).toHaveBeenCalledTimes(1)
    expect(mockState.applyPreset.mock.calls.length).toBe(initialLoadCalls)

    await wrapper.get('[data-testid="viewer-color-select"]').setValue('uncertainty')
    await flushPromises()
    expect(mockState.updateRepresentationsTheme).toHaveBeenCalledWith(
      [{ ref: 'comp-1' }],
      { color: 'uncertainty' },
    )

    await wrapper.get('[data-testid="viewer-bg-toggle"]').trigger('click')
    expect(wrapper.classes()).toContain('molecule-viewer--bg-white')
    expect(mockState.setBackground).toHaveBeenLastCalledWith(expect.anything(), 'white')

    await wrapper.get('[data-testid="viewer-screenshot"]').trigger('click')
    expect(mockState.downloadScreenshot).toHaveBeenCalledWith(expect.anything(), 'target.pdb.png')

    await wrapper.findAll('[data-testid="sequence-residue-btn"]')[0]!.trigger('click')
    await flushPromises()
    expect(mockState.tryCreateComponentFromExpression).toHaveBeenCalled()
    expect(mockState.addRepresentation).toHaveBeenCalled()

    await wrapper.get('[data-testid="viewer-spin-toggle"]').trigger('click')
    expect(wrapper.get('[data-testid="viewer-spin-toggle"]').attributes('aria-pressed')).toBe('true')
    await wrapper.get('[data-testid="viewer-layer-receptor"]').trigger('click')
    expect(wrapper.get('[data-testid="viewer-layer-receptor"]').attributes('aria-pressed')).toBe('false')
    expect(mockState.resetCamera).not.toHaveBeenCalled()
  })

  it('renders docking receptor as polymer-cartoon and non-primary SDF ligand as atomic-detail', async () => {
    const wrapper = mount(MoleculeViewer, {
      props: {
        scene: buildDockingScene(),
        mode: 'docking',
        variant: 'full',
      },
      global: {
        stubs: {
          ASpin: true,
          AAlert: true,
        },
      },
    })

    await flushPromises()

    expect(wrapper.find('.viewer-mode').text()).toBe('tasks.visualizationModes.docking')
    expect(mockState.applyPreset).toHaveBeenCalledTimes(2)
    expect(mockState.applyPreset).toHaveBeenNthCalledWith(
      1,
      expect.anything(),
      'default',
      expect.objectContaining({
        representationPreset: 'polymer-cartoon',
      }),
    )
    expect(mockState.applyPreset).toHaveBeenNthCalledWith(
      2,
      expect.anything(),
      'default',
      expect.objectContaining({
        representationPreset: 'atomic-detail',
      }),
    )
  })

  it('renders the movie playback bar and remaps frames in place without reloading the scene', async () => {
    mockState.trajectoryFrameCount = 25
    const wrapper = mount(MoleculeViewer, {
      props: {
        scene: buildMovieScene({ preferComplexRepresentation: true }),
        mode: 'protein',
        variant: 'full',
        frameTimesPs: Array.from({ length: 25 }, (_, index) => index * 2),
      },
      global: {
        stubs: {
          ASpin: true,
          AAlert: true,
        },
      },
    })

    await flushPromises()

    expect(mockState.applyPreset).toHaveBeenCalledTimes(1)
    expect(mockState.applyPreset).toHaveBeenCalledWith(
      expect.anything(),
      'default',
      expect.objectContaining({ representationPreset: 'polymer-and-ligand' }),
    )
    expect(wrapper.find('[data-testid="viewer-traj-bar"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="viewer-traj-counter"]').text()).toBe('1 / 25 · 0 ps')

    await wrapper.get('[data-testid="viewer-traj-next"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[data-testid="viewer-traj-counter"]').text()).toBe('2 / 25 · 2 ps')
    expect(wrapper.emitted('frame-change')?.[0]).toEqual([1])
    expect(mockState.updateModel).toHaveBeenCalledWith({ modelIndex: 1 })
    expect(mockState.stateUpdate).toHaveBeenCalledTimes(1)
    // 帧切换不触发重新下载/重建，applyPreset 仍只调用一次。
    expect(mockState.applyPreset).toHaveBeenCalledTimes(1)

    await wrapper.get('[data-testid="viewer-traj-prev"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[data-testid="viewer-traj-counter"]').text()).toBe('1 / 25 · 0 ps')
    expect(mockState.updateModel).toHaveBeenLastCalledWith({ modelIndex: 0 })
  })

  it('hides the playback bar and keeps polymer-cartoon for single-frame legacy tasks', async () => {
    const wrapper = mount(MoleculeViewer, {
      props: {
        scene: buildMovieScene(),
        mode: 'protein',
        variant: 'full',
      },
      global: {
        stubs: {
          ASpin: true,
          AAlert: true,
        },
      },
    })

    await flushPromises()

    expect(wrapper.find('[data-testid="viewer-traj-bar"]').exists()).toBe(false)
    expect(mockState.applyPreset).toHaveBeenCalledWith(
      expect.anything(),
      'default',
      expect.objectContaining({ representationPreset: 'polymer-cartoon' }),
    )
  })

  it('hides the playback bar in compact variant even when the movie is multi-frame', async () => {
    mockState.trajectoryFrameCount = 25
    const wrapper = mount(MoleculeViewer, {
      props: {
        scene: buildMovieScene(),
        mode: 'protein',
        variant: 'compact',
      },
      global: {
        stubs: {
          ASpin: true,
          AAlert: true,
        },
      },
    })

    await flushPromises()
    expect(wrapper.find('[data-testid="viewer-traj-bar"]').exists()).toBe(false)
  })

  it('pauses autoplay when the slider is dragged and jumps to the requested frame', async () => {
    mockState.trajectoryFrameCount = 10
    const wrapper = mount(MoleculeViewer, {
      props: {
        scene: buildMovieScene({ preferComplexRepresentation: true }),
        mode: 'protein',
        variant: 'full',
      },
      global: {
        stubs: {
          ASpin: true,
          AAlert: true,
        },
      },
    })

    await flushPromises()

    await wrapper.get('[data-testid="viewer-traj-play"]').trigger('click')
    expect(wrapper.get('[data-testid="viewer-traj-play"]').attributes('aria-pressed')).toBe('true')

    await wrapper.get('[data-testid="viewer-traj-slider"]').setValue('6')
    await flushPromises()

    expect(wrapper.get('[data-testid="viewer-traj-play"]').attributes('aria-pressed')).toBe('false')
    expect(wrapper.get('[data-testid="viewer-traj-counter"]').text()).toBe('7 / 10')
    expect(mockState.updateModel).toHaveBeenLastCalledWith({ modelIndex: 6 })
  })

  it('clears the playback interval on unmount', async () => {
    mockState.trajectoryFrameCount = 10
    const clearIntervalSpy = vi.spyOn(globalThis, 'clearInterval')
    const wrapper = mount(MoleculeViewer, {
      props: {
        scene: buildMovieScene({ preferComplexRepresentation: true }),
        mode: 'protein',
        variant: 'full',
      },
      global: {
        stubs: {
          ASpin: true,
          AAlert: true,
        },
      },
    })

    await flushPromises()
    await wrapper.get('[data-testid="viewer-traj-play"]').trigger('click')
    expect(wrapper.get('[data-testid="viewer-traj-play"]').attributes('aria-pressed')).toBe('true')

    wrapper.unmount()
    expect(clearIntervalSpy).toHaveBeenCalled()
    clearIntervalSpy.mockRestore()
  })

  it('emits export-movie only when the movie export is enabled', async () => {
    mockState.trajectoryFrameCount = 10
    const wrapper = mount(MoleculeViewer, {
      props: {
        scene: buildMovieScene(),
        mode: 'protein',
        variant: 'full',
        canExportMovie: true,
      },
      global: {
        stubs: {
          ASpin: true,
          AAlert: true,
        },
      },
    })

    await flushPromises()
    expect(wrapper.find('[data-testid="viewer-traj-export"]').exists()).toBe(true)
    await wrapper.get('[data-testid="viewer-traj-export"]').trigger('click')
    expect(wrapper.emitted('export-movie')).toHaveLength(1)
  })

  it('keeps frame, counter and slider DOM when the Mol* update rejects, and retries the same frame', async () => {
    mockState.trajectoryFrameCount = 10
    const wrapper = mount(MoleculeViewer, {
      props: {
        scene: buildMovieScene({ preferComplexRepresentation: true }),
        mode: 'protein',
        variant: 'full',
      },
      global: { stubs: { ASpin: true, AAlert: true } },
    })
    await flushPromises()
    const slider = () => wrapper.get('[data-testid="viewer-traj-slider"]').element as HTMLInputElement

    mockState.stateUpdate.mockRejectedValueOnce(new Error('remap rejected'))
    await wrapper.get('[data-testid="viewer-traj-slider"]').setValue('5')
    await flushPromises()

    // 更新被 reject：帧号不得前进、不出 frame-change，被用户拖走的滑块必须回弹到底层帧。
    expect(wrapper.get('[data-testid="viewer-traj-counter"]').text()).toBe('1 / 10')
    expect(wrapper.emitted('frame-change')).toBeUndefined()
    expect(slider().value).toBe('0')

    // 允许再次选择同一目标帧并成功提交。
    await wrapper.get('[data-testid="viewer-traj-slider"]').setValue('5')
    await flushPromises()
    expect(wrapper.get('[data-testid="viewer-traj-counter"]').text()).toBe('6 / 10')
    expect(wrapper.emitted('frame-change')).toEqual([[5]])
    expect(slider().value).toBe('5')
    expect(mockState.updateModel).toHaveBeenLastCalledWith({ modelIndex: 5 })
  })

  it('treats an Update that resolves with an error cell as a failed frame change, rolls back modelIndex, then retries cleanly', async () => {
    mockState.trajectoryFrameCount = 10
    const wrapper = mount(MoleculeViewer, {
      props: {
        scene: buildMovieScene({ preferComplexRepresentation: true }),
        mode: 'protein',
        variant: 'full',
      },
      global: { stubs: { ASpin: true, AAlert: true } },
    })
    await flushPromises()
    const slider = () => wrapper.get('[data-testid="viewer-traj-slider"]').element as HTMLInputElement

    // 真实 Mol* 形态：Update 写入 modelIndex=6 时 cell 首次进入 error，回写 modelIndex=0 时恢复正常；
    // 即使下一次再选同一帧 6 成功，也必须依赖失败时已把 modelIndex 回写为 0。
    let failFirstWriteToSix = true
    mockState.updateModel.mockImplementation((payload: Record<string, unknown>) => {
      if (payload.modelIndex === 6 && failFirstWriteToSix) {
        failFirstWriteToSix = false
        mockState.cells.set('model-ref-1', { status: 'error' })
      } else {
        mockState.cells.delete('model-ref-1')
      }
    })

    await wrapper.get('[data-testid="viewer-traj-slider"]').setValue('6')
    await flushPromises()

    expect(mockState.updateModel.mock.calls.map(call => call[0])).toEqual([
      { modelIndex: 6 },
      { modelIndex: 0 },
    ])
    expect(mockState.stateUpdate).toHaveBeenCalledTimes(2)
    expect(wrapper.get('[data-testid="viewer-traj-counter"]').text()).toBe('1 / 10')
    expect(wrapper.emitted('frame-change')).toBeUndefined()
    expect(slider().value).toBe('0')

    // 重选同一帧 6 时，因状态树之前已回滚到 0（无需手工清 mock），参数变化会再次触发更新并成功。
    await wrapper.get('[data-testid="viewer-traj-slider"]').setValue('6')
    await flushPromises()
    expect(mockState.updateModel).toHaveBeenLastCalledWith({ modelIndex: 6 })
    expect(wrapper.get('[data-testid="viewer-traj-counter"]').text()).toBe('7 / 10')
    expect(wrapper.emitted('frame-change')).toEqual([[6]])
    expect(slider().value).toBe('6')
  })

  it('snaps slider back to committed frame when manual scrub fails even if a stale auto frame was queued and paused', async () => {
    vi.useFakeTimers()
    mockState.trajectoryFrameCount = 10
    const manualInFlight = deferred()
    mockState.stateUpdate.mockImplementationOnce(() => manualInFlight.promise)

    const wrapper = mount(MoleculeViewer, {
      props: {
        scene: buildMovieScene({ preferComplexRepresentation: true }),
        mode: 'protein',
        variant: 'full',
      },
      global: { stubs: { ASpin: true, AAlert: true } },
    })
    await flushPromises()
    const slider = () => wrapper.get('[data-testid="viewer-traj-slider"]').element as HTMLInputElement

    // 1. 手动拖到索引 5（Update 处于在途阶段）
    await wrapper.get('[data-testid="viewer-traj-slider"]').setValue('5')
    expect(mockState.stateUpdate).toHaveBeenCalledTimes(1)
    expect(slider().value).toBe('5')

    // 2. 更新完成前开启播放并触发定时器，再立即暂停（自动帧曾入队但已过期）
    await wrapper.get('[data-testid="viewer-traj-play"]').trigger('click')
    await vi.advanceTimersByTimeAsync(computeFrameIntervalMs(1))
    await wrapper.get('[data-testid="viewer-traj-play"]').trigger('click')

    // 3. 保持/恢复用户在原生滑块上的拖动手柄位置为 5（避免播放暂停重渲染掩盖回弹路径），
    // 手动更新随后被 reject：原生滑块必须立刻回弹到 0，且过期自动帧不得提交
    slider().value = '5'
    expect(slider().value).toBe('5')
    manualInFlight.reject(new Error('manual frame failed'))
    await flushPromises()

    expect(wrapper.get('[data-testid="viewer-traj-counter"]').text()).toBe('1 / 10')
    expect(wrapper.emitted('frame-change')).toBeUndefined()
    expect(slider().value).toBe('0')
    expect(mockState.stateUpdate).toHaveBeenCalledTimes(1)
  })

  it('rolls the Mol* state tree back to the committed frame when autoplay is paused mid-update', async () => {
    vi.useFakeTimers()
    mockState.trajectoryFrameCount = 10
    const inFlight = deferred()
    mockState.stateUpdate.mockImplementationOnce(() => inFlight.promise)
    const wrapper = mount(MoleculeViewer, {
      props: {
        scene: buildMovieScene({ preferComplexRepresentation: true }),
        mode: 'protein',
        variant: 'full',
      },
      global: { stubs: { ASpin: true, AAlert: true } },
    })
    await flushPromises()

    await wrapper.get('[data-testid="viewer-traj-play"]').trigger('click')
    // 第一帧 Update 在途；下一次 tick 只能排进 pendingFrameRequest，不能并发提交。
    await vi.advanceTimersByTimeAsync(computeFrameIntervalMs(1))
    await vi.advanceTimersByTimeAsync(computeFrameIntervalMs(1))
    expect(mockState.stateUpdate).toHaveBeenCalledTimes(1)

    await wrapper.get('[data-testid="viewer-traj-play"]').trigger('click')
    expect(wrapper.get('[data-testid="viewer-traj-play"]').attributes('aria-pressed')).toBe('false')

    inFlight.resolve()
    await flushPromises()

    // 暂停后计数/事件/状态树都必须停在旧帧：在途更新成功后要写回 modelIndex 0。
    expect(wrapper.get('[data-testid="viewer-traj-counter"]').text()).toBe('1 / 10')
    expect(wrapper.emitted('frame-change')).toBeUndefined()
    expect(mockState.updateModel).toHaveBeenLastCalledWith({ modelIndex: 0 })
    expect(mockState.stateUpdate).toHaveBeenCalledTimes(2)
    expect((wrapper.get('[data-testid="viewer-traj-slider"]').element as HTMLInputElement).value).toBe('0')

    // 暂停后定时器已清除，排队中的自动帧也不会再提交。
    await vi.advanceTimersByTimeAsync(computeFrameIntervalMs(1) * 4)
    expect(mockState.stateUpdate).toHaveBeenCalledTimes(2)
    expect(wrapper.get('[data-testid="viewer-traj-counter"]').text()).toBe('1 / 10')
  })

  it('rolls the Mol* state tree back when the speed changes mid-update', async () => {
    vi.useFakeTimers()
    mockState.trajectoryFrameCount = 10
    const inFlight = deferred()
    mockState.stateUpdate.mockImplementationOnce(() => inFlight.promise)
    const wrapper = mount(MoleculeViewer, {
      props: {
        scene: buildMovieScene({ preferComplexRepresentation: true }),
        mode: 'protein',
        variant: 'full',
      },
      global: { stubs: { ASpin: true, AAlert: true } },
    })
    await flushPromises()

    await wrapper.get('[data-testid="viewer-traj-play"]').trigger('click')
    await vi.advanceTimersByTimeAsync(computeFrameIntervalMs(1))
    await vi.advanceTimersByTimeAsync(computeFrameIntervalMs(1))
    expect(mockState.stateUpdate).toHaveBeenCalledTimes(1)

    await wrapper.get('[data-testid="viewer-traj-speed"]').setValue('2')
    expect(wrapper.get('[data-testid="viewer-traj-play"]').attributes('aria-pressed')).toBe('true')

    inFlight.resolve()
    await flushPromises()
    expect(wrapper.get('[data-testid="viewer-traj-counter"]').text()).toBe('1 / 10')
    expect(wrapper.emitted('frame-change')).toBeUndefined()
    expect(mockState.updateModel).toHaveBeenLastCalledWith({ modelIndex: 0 })
    expect(mockState.stateUpdate).toHaveBeenCalledTimes(2)
  })

  it('rolls the Mol* state tree back when looping is toggled mid-update', async () => {
    vi.useFakeTimers()
    mockState.trajectoryFrameCount = 10
    const inFlight = deferred()
    mockState.stateUpdate.mockImplementationOnce(() => inFlight.promise)
    const wrapper = mount(MoleculeViewer, {
      props: {
        scene: buildMovieScene({ preferComplexRepresentation: true }),
        mode: 'protein',
        variant: 'full',
      },
      global: { stubs: { ASpin: true, AAlert: true } },
    })
    await flushPromises()

    await wrapper.get('[data-testid="viewer-traj-play"]').trigger('click')
    await vi.advanceTimersByTimeAsync(computeFrameIntervalMs(1))
    await vi.advanceTimersByTimeAsync(computeFrameIntervalMs(1))
    expect(mockState.stateUpdate).toHaveBeenCalledTimes(1)

    await wrapper.get('[data-testid="viewer-traj-loop"]').trigger('click')
    expect(wrapper.get('[data-testid="viewer-traj-loop"]').attributes('aria-pressed')).toBe('false')

    inFlight.resolve()
    await flushPromises()
    expect(wrapper.get('[data-testid="viewer-traj-counter"]').text()).toBe('1 / 10')
    expect(wrapper.emitted('frame-change')).toBeUndefined()
    expect(mockState.updateModel).toHaveBeenLastCalledWith({ modelIndex: 0 })
    expect(mockState.stateUpdate).toHaveBeenCalledTimes(2)
  })

  it('keeps polymer-cartoon for multi-frame PDB previews without the complex flag', async () => {
    mockState.trajectoryFrameCount = 5
    const wrapper = mount(MoleculeViewer, {
      props: {
        scene: buildMovieScene(),
        mode: 'protein',
        variant: 'full',
      },
      global: { stubs: { ASpin: true, AAlert: true } },
    })

    await flushPromises()
    expect(wrapper.find('[data-testid="viewer-traj-bar"]').exists()).toBe(true)
    expect(mockState.applyPreset).toHaveBeenCalledWith(
      expect.anything(),
      'default',
      expect.objectContaining({ representationPreset: 'polymer-cartoon' }),
    )
  })

  it('syncs every playable entry and ignores a leading multi-frame entry without modelRef', async () => {
    mockState.frameCountQueue = [3, 5, 2]
    mockState.presetQueue = [
      { structure: { ref: 's-receptor' } },
      { structure: { ref: 's-movie-2' }, model: { ref: 'm-movie-2' } },
      { structure: { ref: 's-movie-3' }, model: { ref: 'm-movie-3' } },
    ]
    const wrapper = mount(MoleculeViewer, {
      props: {
        scene: buildMultiMovieScene(),
        mode: 'protein',
        variant: 'full',
      },
      global: { stubs: { ASpin: true, AAlert: true } },
    })
    await flushPromises()

    expect(mockState.applyPreset).toHaveBeenCalledTimes(3)
    expect(wrapper.find('[data-testid="viewer-traj-bar"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="viewer-traj-counter"]').text()).toBe('1 / 5')

    await wrapper.get('[data-testid="viewer-traj-next"]').trigger('click')
    await flushPromises()
    expect(mockState.updateCalls).toEqual([
      { ref: 'm-movie-2', payload: { modelIndex: 1 } },
      { ref: 'm-movie-3', payload: { modelIndex: 1 } },
    ])

    // 帧数较少的条目按自身 frameCount 收敛到末帧，不越界。
    await wrapper.get('[data-testid="viewer-traj-next"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-testid="viewer-traj-next"]').trigger('click')
    await flushPromises()
    expect(mockState.updateCalls.slice(-2)).toEqual([
      { ref: 'm-movie-2', payload: { modelIndex: 3 } },
      { ref: 'm-movie-3', payload: { modelIndex: 1 } },
    ])
  })

  it('treats a failed representation cell as a failed frame and stops playback', async () => {
    vi.useFakeTimers()
    mockState.trajectoryFrameCount = 5
    mockState.presetQueue = [
      {
        structure: { ref: 'structure-ref-movie' },
        model: { ref: 'model-ref-movie' },
        representation: { representations: { 'polymer-cartoon': { ref: 'rep-ref-movie' } } },
      },
    ]
    const wrapper = mount(MoleculeViewer, {
      props: {
        scene: buildMovieScene(),
        mode: 'protein',
        variant: 'full',
      },
      global: { stubs: { ASpin: true, AAlert: true } },
    })
    await flushPromises()
    expect(wrapper.get('[data-testid="viewer-traj-counter"]').text()).toBe('1 / 5')

    // Mol* 可能只把 representation 节点置为 error，model/structure 仍为 ok：
    // 这同样意味着新帧没有完整渲染，不能提交帧号。
    mockState.cells.set('rep-ref-movie', { status: 'error' })

    await wrapper.get('[data-testid="viewer-traj-play"]').trigger('click')
    await vi.advanceTimersByTimeAsync(computeFrameIntervalMs(1))
    await vi.advanceTimersByTimeAsync(computeFrameIntervalMs(1))

    expect(wrapper.get('[data-testid="viewer-traj-counter"]').text()).toBe('1 / 5')
    expect(wrapper.get('[data-testid="viewer-traj-play"]').attributes('aria-pressed')).toBe('false')
    expect(wrapper.emitted('frame-change')).toBeUndefined()
    expect(mockState.updateModel).toHaveBeenLastCalledWith({ modelIndex: 0 })
  })

  it('checks representation cells rebuilt by a later style switch', async () => {
    vi.useFakeTimers()
    mockState.trajectoryFrameCount = 5
    mockState.presetQueue = [
      {
        structure: { ref: 'structure-ref-movie' },
        model: { ref: 'model-ref-movie' },
        representation: { representations: { 'polymer-cartoon': { ref: 'rep-ref-initial' } } },
      },
    ]
    mockState.hierarchyStructures = [
      {
        cell: { transform: { ref: 'structure-ref-movie' }, obj: { data: { id: 'mock-structure' } } },
        components: [
          {
            ref: 'comp-movie',
            representations: [{ cell: { transform: { ref: 'rep-ref-initial' } } }],
          },
        ],
      },
    ]
    const wrapper = mount(MoleculeViewer, {
      props: {
        scene: buildMovieScene(),
        mode: 'protein',
        variant: 'full',
      },
      global: { stubs: { ASpin: true, AAlert: true } },
    })
    await flushPromises()
    expect(wrapper.get('[data-testid="viewer-traj-counter"]').text()).toBe('1 / 5')

    // 切换样式会销毁初始 representation 并新建节点；换帧校验必须读新节点。
    mockState.addRepresentation.mockImplementationOnce(async () => {
      setLiveRepresentations('structure-ref-movie', ['rep-ref-spacefill'])
    })
    await wrapper.get('[data-testid="viewer-representation-select"]').setValue('spacefill')
    await flushPromises()

    mockState.cells.set('rep-ref-spacefill', { status: 'error' })

    await wrapper.get('[data-testid="viewer-traj-play"]').trigger('click')
    await vi.advanceTimersByTimeAsync(computeFrameIntervalMs(1))
    await vi.advanceTimersByTimeAsync(computeFrameIntervalMs(1))

    expect(wrapper.get('[data-testid="viewer-traj-counter"]').text()).toBe('1 / 5')
    expect(wrapper.get('[data-testid="viewer-traj-play"]').attributes('aria-pressed')).toBe('false')
    expect(wrapper.emitted('frame-change')).toBeUndefined()
    expect(mockState.updateModel).toHaveBeenLastCalledWith({ modelIndex: 0 })
  })

  it('emits entry-unavailable for one broken fallback entry and still renders the rest', async () => {
    mockState.applyPreset.mockRejectedValueOnce(new Error('empty movie file'))
    const wrapper = mount(MoleculeViewer, {
      props: {
        scene: buildFallbackScene(),
        mode: 'protein',
        variant: 'full',
      },
      global: { stubs: { ASpin: true, AAlert: true } },
    })
    await flushPromises()

    expect(wrapper.emitted('entry-unavailable')).toEqual([['movie-1']])
    expect(mockState.applyPreset).toHaveBeenCalledTimes(2)
    expect(wrapper.find('.viewer-overlay--error').exists()).toBe(false)
  })

  it('waits for a delayed Mol* frame update to finish before disposing on unmount', async () => {
    mockState.trajectoryFrameCount = 10
    const pending = deferred()
    mockState.stateUpdate.mockImplementationOnce(() => pending.promise)
    const wrapper = mount(MoleculeViewer, {
      props: {
        scene: buildMovieScene({ preferComplexRepresentation: true }),
        mode: 'protein',
        variant: 'full',
      },
      global: { stubs: { ASpin: true, AAlert: true } },
    })
    await flushPromises()

    await wrapper.get('[data-testid="viewer-traj-next"]').trigger('click')
    await flushPromises()
    expect(mockState.stateUpdate).toHaveBeenCalledTimes(1)

    wrapper.unmount()
    await flushPromises()
    // 在途 Update 未结束前不得销毁 viewer，避免与 `viewer.dispose()` 撞车。
    expect(mockState.disposeViewer).not.toHaveBeenCalled()

    pending.resolve()
    await flushPromises()

    expect(mockState.disposeViewer).toHaveBeenCalledTimes(1)
    expect(wrapper.emitted('frame-change')).toBeUndefined()
  })
})
