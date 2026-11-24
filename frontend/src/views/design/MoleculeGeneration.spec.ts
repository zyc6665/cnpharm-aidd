import { ref } from 'vue'
import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import MoleculeGeneration from './MoleculeGeneration.vue'

const mocks = vi.hoisted(() => ({ load: vi.fn().mockResolvedValue(undefined) }))
vi.mock('vue-i18n', () => ({ useI18n: () => ({ t: (key: string) => key }) }))
vi.mock('vue-router', () => ({ useRoute: () => ({ query: {} }), useRouter: () => ({ push: vi.fn() }) }))
vi.mock('@/api/design', () => ({ resolveToolBySlug: vi.fn().mockResolvedValue(null), submitDesignTask: vi.fn() }))
vi.mock('@/api/projects', () => ({ listProjects: vi.fn().mockResolvedValue({ data: { items: [] } }) }))
vi.mock('@/composables/useModelOptions', () => ({ useModelOptions: () => ({ options: ref([]), selectedSlug: ref('pocket2mol-pocket-ligand-generation'), selectedOption: ref(null), loading: ref(false), load: mocks.load }) }))

describe('MoleculeGeneration', () => {
  it('renders the generation page', () => {
    const wrapper = mount(MoleculeGeneration, { global: { stubs: { PocketPicker: true, AppPageHeader: true, ModelSelect: true, ModelParameterForm: true, ParameterPresets: true, TaskProgressCard: true, 'a-alert': true, 'a-radio-button': true, 'a-radio-group': true, 'a-select': true, 'a-button': true, 'a-upload': true, 'a-descriptions-item': true, 'a-descriptions': true, 'a-spin': true } } })
    expect(wrapper.find('[data-testid="molecule-generation-page"]').exists()).toBe(true)
  })
})
