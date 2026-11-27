import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import Pockets from './Pockets.vue'

const pushMock = vi.fn()
const listPocketsMock = vi.fn()
const selectPocketMock = vi.fn()
const getStructureMock = vi.fn()
const getProteinMock = vi.fn()
const getTargetMock = vi.fn()

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { structureId: 's-1' } }),
  useRouter: () => ({ push: pushMock }),
}))

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (key: string) => key }),
}))

vi.mock('ant-design-vue', () => ({
  message: { success: vi.fn(), error: vi.fn() },
}))

vi.mock('@/api/targets', () => ({
  listPockets: (...args: unknown[]) => listPocketsMock(...args),
  selectPocket: (...args: unknown[]) => selectPocketMock(...args),
  getStructure: (...args: unknown[]) => getStructureMock(...args),
  getProtein: (...args: unknown[]) => getProteinMock(...args),
  getTarget: (...args: unknown[]) => getTargetMock(...args),
}))

describe('Pockets.vue handoff', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    listPocketsMock.mockResolvedValue({
      data: {
        items: [
          {
            id: 'pk-1',
            rank: 1,
            score: 0.92,
            selected: true,
            center: { x: 10.5, y: -2.25, z: 4.75 },
            volume: 420,
          },
        ],
      },
    })
    getStructureMock.mockResolvedValue({ data: { id: 's-1', protein_id: 'pr-1' } })
    getProteinMock.mockResolvedValue({ data: { id: 'pr-1', target_id: 't-1' } })
    getTargetMock.mockResolvedValue({ data: { id: 't-1', project_id: 'p-1' } })
  })

  function mountPage() {
    return mount(Pockets, {
      global: {
        stubs: {
          AppBackLink: true,
          AppPageHeader: { template: '<div><slot name="actions" /></div>' },
          AppErrorState: true,
          AppEmptyState: true,
          SkeletonList: true,
          ResultDisclaimer: true,
          'a-table': true,
          'a-tag': true,
          'a-button': {
            emits: ['click'],
            template: '<button @click="$emit(\'click\', $event)"><slot /></button>',
          },
        },
      },
    })
  }

  it('navigates to MoleculeGeneration and ScreenConfig with full target/pocket query context', async () => {
    const wrapper = mountPage()
    await flushPromises()

    await wrapper.get('[data-testid="pockets-handoff-generation"]').trigger('click')
    expect(pushMock).toHaveBeenCalledWith({
      name: 'MoleculeGeneration',
      query: {
        project_id: 'p-1',
        target_id: 't-1',
        protein_id: 'pr-1',
        structure_id: 's-1',
        pocket_id: 'pk-1',
        center_x: '10.5',
        center_y: '-2.25',
        center_z: '4.75',
      },
    })

    await wrapper.get('[data-testid="pockets-handoff-screening"]').trigger('click')
    expect(pushMock).toHaveBeenLastCalledWith({
      name: 'ScreenConfig',
      query: {
        project_id: 'p-1',
        target_id: 't-1',
        protein_id: 'pr-1',
        structure_id: 's-1',
        pocket_id: 'pk-1',
        center_x: '10.5',
        center_y: '-2.25',
        center_z: '4.75',
      },
    })
  })
})
