import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import i18n from '@/locales'

const { push, loadMoleculeTable, getTaskDetail } = vi.hoisted(() => ({ push: vi.fn(), loadMoleculeTable: vi.fn(), getTaskDetail: vi.fn() }))
vi.mock('vue-router', () => ({ useRoute: () => ({ params: { id: 'task-1' }, query: {}, fullPath: '/screening/task-1/result' }), useRouter: () => ({ push }) }))
vi.mock('@/views/predict/molecule-table', () => ({ loadMoleculeTable }))
vi.mock('@/api/tasks', () => ({ getTaskDetail }))
vi.mock('@/api/compounds', () => ({ addCandidateSetItems: vi.fn(), createCandidate: vi.fn(), createCandidateSet: vi.fn() }))
vi.mock('@/api/files', () => ({ uploadFile: vi.fn() }))
vi.mock('@/api/task-events', () => ({ openTaskEventStream: vi.fn() }))
vi.mock('ant-design-vue', () => ({ message: { success: vi.fn(), warning: vi.fn(), error: vi.fn() } }))
import ScreenResult from './ScreenResult.vue'

const stubs = { AppPageHeader: { template: '<div><slot name="actions" /></div>' }, TaskContextBar: true, ResultDisclaimer: true, FunnelChart: true, 'a-space': { template: '<div><slot /></div>' }, 'a-button': { props: ['disabled'], template: '<button :disabled="disabled"><slot /></button>' }, 'a-alert': true, 'a-empty': true, 'a-row': { template: '<div><slot /></div>' }, 'a-col': { template: '<div><slot /></div>' }, 'a-card': { template: '<div><slot /></div>' }, 'a-table': { props: ['dataSource', 'rowKey'], template: '<div data-testid="screen-result-table">{{ dataSource?.length }}</div>' }, 'a-statistic': true, 'a-tag': true, 'a-modal': true, 'a-form': { template: '<div><slot /></div>' }, 'a-form-item': { template: '<div><slot /></div>' }, 'a-input': true, 'a-spin': true }

describe('ScreenResult', () => {
  beforeEach(() => { loadMoleculeTable.mockReset().mockResolvedValue({ rows: [{ __rowKey: '0', rank: '1', smiles: 'CCO' }], detail: { project_id: 'p1' } }); getTaskDetail.mockReset() })
  it('loads results and exposes ADMET and MD handoff actions', async () => {
    getTaskDetail.mockResolvedValue({
      data: {
        id: 'task-1',
        project_id: 'p1',
        input_snapshots: [{ inputRole: 'receptor_pdb', entityType: 'protein_structure', entityId: 'struct-9', fileId: 'file-9', detail: { target_id: 'targ-9', protein_id: 'prot-9' } }]
      }
    })
    const wrapper = mount(ScreenResult, { global: { plugins: [i18n], stubs } })
    await flushPromises()
    expect(wrapper.find('[data-testid="screen-result-page"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="screen-send-admet"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="screen-send-md"]').exists()).toBe(true)
    await wrapper.get('[data-testid="screen-send-md"]').trigger('click')
    await flushPromises()
    expect(push).toHaveBeenCalledWith({
      path: '/md',
      query: { project_id: 'p1', target_id: 'targ-9', protein_id: 'prot-9', structure_id: 'struct-9' }
    })
  })
  it('omits structure_id for file-only receptor without passing fileId as structure_id', async () => {
    getTaskDetail.mockResolvedValue({
      data: { id: 'task-1', project_id: 'p1', input_snapshots: [{ inputRole: 'receptor_pdb', entityType: 'file', entityId: 'file-9', fileId: 'file-9' }] }
    })
    const wrapper = mount(ScreenResult, { global: { plugins: [i18n], stubs } })
    await flushPromises()
    await wrapper.get('[data-testid="screen-send-md"]').trigger('click')
    await flushPromises()
    expect(push).toHaveBeenCalledWith({ path: '/md', query: { project_id: 'p1' } })
  })
})
