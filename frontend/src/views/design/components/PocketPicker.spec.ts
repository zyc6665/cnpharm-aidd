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
vi.mock('@/components/design/StructurePredictForm.vue', () => ({
  default: { template: '<div data-testid="structure-predict-form" />' },
}))
vi.mock('@/components/design/PocketPredictPanel.vue', () => ({
  default: { template: '<div data-testid="pocket-predict-panel" />' },
}))
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
})
