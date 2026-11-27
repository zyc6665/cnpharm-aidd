import { describe, it, expect, vi, beforeEach } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import i18n from '@/locales'

vi.mock('@/api/design', () => ({
  listDesignProjects: vi.fn().mockResolvedValue([{ id: 'p1', name: 'P1' }]),
  listProjectTargets: vi.fn().mockResolvedValue([{ id: 't1', name: 'T' }]),
  loadTargetProteins: vi.fn().mockResolvedValue([{ id: 'pr1', name: 'P' }]),
  listProteinStructures: vi.fn().mockResolvedValue([{ id: 's1', source_type: 'predicted' }]),
  listStructurePockets: vi.fn().mockResolvedValue([]),
}))
vi.mock('@/api/files', () => ({
  getFileInfo: vi.fn().mockRejectedValue(new Error('not mocked')),
}))
vi.mock('@/components/design/StructurePredictForm.vue', () => ({
  default: { template: '<div data-testid="structure-predict-form" />' },
}))
vi.mock('@/components/design/PocketPredictPanel.vue', () => ({
  default: { template: '<div data-testid="pocket-predict-panel" />' },
}))
import { getFileInfo } from '@/api/files'
import PocketPicker from './PocketPicker.vue'
import type { DesignPocketSelection } from '@/types/design'
import type { VisualizationScene } from '@/domain/tasks'

const ViewerStub = {
  name: 'PocketPreviewViewer',
  props: { scene: { type: Object, required: true } },
  template: '<div data-testid="molecule-viewer-stub" />',
}

function selection(overrides: Partial<DesignPocketSelection> = {}): DesignPocketSelection {
  return {
    projectId: 'p1',
    targetId: 't1',
    proteinId: 'pr1',
    structureId: 's1',
    pocketId: 'pk1',
    pocketLabel: '#1',
    score: 0.8,
    structureFileId: 'file-1',
    structureUrn: 'file:receptor.pdb',
    center: { x: 1, y: 2, z: 3 },
    boxSize: { x: 20, y: 20, z: 20 },
    ...overrides,
  }
}

function mountWithPreview(value: DesignPocketSelection) {
  return mount(PocketPicker, {
    props: { modelValue: value, showPreview: true },
    global: {
      plugins: [i18n],
      stubs: { PocketPreviewViewer: ViewerStub },
    },
  })
}

function viewerScene(wrapper: Awaited<ReturnType<typeof mountWithPreview>>): VisualizationScene {
  return wrapper.findComponent(ViewerStub).props('scene') as VisualizationScene
}

describe('PocketPicker', () => {
  beforeEach(() => vi.clearAllMocks())

  it('renders a stepper', () => {
    const w = mount(PocketPicker, { props: { modelValue: null }, global: { plugins: [i18n] } })
    expect(w.find('[data-testid="pocket-stepper"]').exists()).toBe(true)
  })

  it('keeps preview disabled by default for backward compatibility', async () => {
    const w = mount(PocketPicker, {
      props: { modelValue: selection() },
      global: { plugins: [i18n] },
    })
    await flushPromises()
    expect(w.find('[data-testid="pocket-preview"]').exists()).toBe(false)
  })

  it('renders a compact 3D preview when enabled and a structure file exists', async () => {
    const w = mountWithPreview(selection())
    await flushPromises()
    expect(w.find('[data-testid="pocket-preview"]').exists()).toBe(true)
    expect(w.find('[data-testid="molecule-viewer-stub"]').exists()).toBe(true)
  })

  it('passes pdb format for .pdb structures', async () => {
    const w = mountWithPreview(selection({ structureUrn: 'file:receptor.pdb' }))
    await flushPromises()

    const [entry] = viewerScene(w).entries
    expect(entry?.format).toBe('pdb')
    expect(entry?.extension).toBe('.pdb')
  })

  it('parses .cif structures as mmcif instead of pdb', async () => {
    const w = mountWithPreview(selection({ structureUrn: 'file:receptor.cif' }))
    await flushPromises()

    const [entry] = viewerScene(w).entries
    expect(entry?.format).toBe('mmcif')
    expect(entry?.extension).toBe('.cif')
  })

  it('keeps .mmcif extension when the URN ends with .mmcif', async () => {
    const w = mountWithPreview(selection({ structureUrn: 's3://bucket/complex.mmcif' }))
    await flushPromises()

    const [entry] = viewerScene(w).entries
    expect(entry?.format).toBe('mmcif')
    expect(entry?.extension).toBe('.mmcif')
  })

  it('hides the viewer and explains unsupported formats', async () => {
    const w = mountWithPreview(selection({ structureUrn: 'file:receptor.xyz' }))
    await flushPromises()

    expect(w.find('[data-testid="molecule-viewer-stub"]').exists()).toBe(false)
    const empty = w.get('[data-testid="pocket-preview-empty"]')
    expect(empty.text()).toContain(i18n.global.t('design.molecule.pocketPreviewUnsupportedFormat'))
  })

  it('resolves format via file metadata when URN is file:<uuid> without extension', async () => {
    vi.mocked(getFileInfo).mockResolvedValueOnce({
      data: { id: 'file-uuid-1', filename: 'boltz2_model.cif' },
    } as never)

    const w = mountWithPreview(
      selection({ structureFileId: 'file-uuid-1', structureUrn: 'file:file-uuid-1' })
    )
    await flushPromises()

    const [entry] = viewerScene(w).entries
    expect(entry?.format).toBe('mmcif')
    expect(entry?.extension).toBe('.cif')
  })

  it('hides the viewer when the structure URN is missing', async () => {
    const w = mountWithPreview(selection({ structureUrn: null }))
    await flushPromises()

    expect(w.find('[data-testid="molecule-viewer-stub"]').exists()).toBe(false)
    expect(w.get('[data-testid="pocket-preview-empty"]').text()).toContain(
      i18n.global.t('design.molecule.pocketPreviewUnsupportedFormat')
    )
  })

  it('shows a clean fallback when the pocket has no structure file', async () => {
    const w = mountWithPreview(selection({ structureFileId: null }))
    await flushPromises()

    expect(w.find('[data-testid="pocket-preview-empty"]').exists()).toBe(true)
    expect(w.find('[data-testid="molecule-viewer-stub"]').exists()).toBe(false)
    expect(w.get('[data-testid="pocket-preview-empty"]').text()).toContain(
      i18n.global.t('design.molecule.pocketPreviewMissing')
    )
  })

  it('resets descendant loading flags when clearing project selection during an in-flight request', async () => {
    const { listProjectTargets } = await import('@/api/design')
    let resolveTargets!: (rows: Array<{ id: string; name: string }>) => void
    vi.mocked(listProjectTargets).mockReturnValueOnce(
      new Promise(resolve => {
        resolveTargets = resolve
      }) as never
    )
    const SelectStub = {
      name: 'ASelectStub',
      props: ['value', 'loading', 'options', 'placeholder', 'disabled', 'allowClear'],
      emits: ['update:value', 'change'],
      template: '<div class="select-stub" :data-loading="String(Boolean(loading))" />',
    }
    const w = mount(PocketPicker, {
      props: { modelValue: null },
      global: { plugins: [i18n], stubs: { 'a-select': SelectStub } },
    })
    await flushPromises()

    const selects = w.findAllComponents(SelectStub)
    selects[0]!.vm.$emit('update:value', 'p1')
    selects[0]!.vm.$emit('change', 'p1')
    await flushPromises()
    expect(w.findAllComponents(SelectStub)[1]!.props('loading')).toBe(true)

    selects[0]!.vm.$emit('update:value', undefined)
    selects[0]!.vm.$emit('change', undefined)
    await flushPromises()
    expect(w.findAllComponents(SelectStub)[1]!.props('loading')).toBe(false)

    resolveTargets([{ id: 't-stale', name: 'Stale' }])
    await flushPromises()
    expect(w.findAllComponents(SelectStub)[1]!.props('loading')).toBe(false)
  })

  it('prefills full target hierarchy including unselected initialPocketId when provided', async () => {
    const { listStructurePockets } = await import('@/api/design')
    const targetPocket = {
      id: 'pk-2',
      rank: 2,
      score: 0.91,
      selected: false,
      center: { x: 11.2, y: -3.4, z: 7.8 },
      box_size: { x: 20, y: 20, z: 20 },
    }
    vi.mocked(listStructurePockets).mockResolvedValueOnce([
      { id: 'pk-1', rank: 1, score: 0.95, selected: true, center: { x: 1, y: 2, z: 3 } },
      targetPocket,
    ] as never)

    const w = mount(PocketPicker, {
      props: {
        modelValue: null,
        projectId: 'p1',
        hideProjectSelect: true,
        initialTargetId: 't1',
        initialProteinId: 'pr1',
        initialStructureId: 's1',
        initialPocketId: 'pk-2',
      },
      global: { plugins: [i18n] },
    })
    await flushPromises()

    expect(listStructurePockets).toHaveBeenCalledWith('s1')
    const emitted = w.emitted('update:modelValue')
    expect(emitted?.[emitted.length - 1]?.[0]).toMatchObject({
      projectId: 'p1',
      targetId: 't1',
      proteinId: 'pr1',
      structureId: 's1',
      pocketId: 'pk-2',
      center: { x: 11.2, y: -3.4, z: 7.8 },
    })
  })
})
