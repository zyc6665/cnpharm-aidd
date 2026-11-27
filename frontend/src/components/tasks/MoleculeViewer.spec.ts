import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import MoleculeViewer from './MoleculeViewer.vue'
import type { VisualizationScene } from '@/domain/tasks'

const mockState = {
  applyPreset: vi.fn(async () => ({ structure: { ref: 'structure-ref-1' } })),
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
          cells: new Map(),
          build: () => ({
            delete: vi.fn(),
            commit: vi.fn(async () => undefined),
          }),
        },
      },
      builders: {
        data: {
          download: vi.fn(async () => ({ ref: 'data-ref' })),
        },
        structure: {
          parseTrajectory: vi.fn(async () => ({ ref: 'traj-ref' })),
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
              structures: [
                {
                  cell: {
                    transform: { ref: 'structure-ref-1' },
                    obj: { data: { id: 'mock-structure' } },
                  },
                  components: [{ ref: 'comp-1' }],
                },
              ],
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
  beforeEach(() => {
    vi.clearAllMocks()
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
})
