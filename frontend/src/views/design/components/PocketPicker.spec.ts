import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
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

describe('PocketPicker', () => {
  beforeEach(() => vi.clearAllMocks())

  it('renders a stepper', () => {
    const w = mount(PocketPicker, { props: { modelValue: null }, global: { plugins: [i18n] } })
    expect(w.find('[data-testid="pocket-stepper"]').exists()).toBe(true)
  })
})
