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
    center: { x: 1, y: 2, z: 3 },
    boxSize: { x: 20, y: 20, z: 20 },
    ...overrides,
  }
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
    const w = mount(PocketPicker, {
      props: { modelValue: selection(), showPreview: true },
      global: {
        plugins: [i18n],
        stubs: {
          PocketPreviewViewer: { template: '<div data-testid="molecule-viewer-stub" />' },
        },
      },
    })
    await flushPromises()
    expect(w.find('[data-testid="pocket-preview"]').exists()).toBe(true)
    expect(w.find('[data-testid="molecule-viewer-stub"]').exists()).toBe(true)
  })

  it('shows a clean fallback when the pocket has no structure file', async () => {
    const w = mount(PocketPicker, {
      props: { modelValue: selection({ structureFileId: null }), showPreview: true },
      global: { plugins: [i18n] },
    })
    await flushPromises()
    expect(w.find('[data-testid="pocket-preview-empty"]').exists()).toBe(true)
    expect(w.find('[data-testid="molecule-viewer-stub"]').exists()).toBe(false)
  })
})
