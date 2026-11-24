import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { filterPredictRows } from './predict-filter'
import i18n from '@/locales'

const { loadMoleculeTable, push, uploadFile, createCandidate, createCandidateSet, addCandidateSetItems } = vi.hoisted(() => ({
  loadMoleculeTable: vi.fn(),
  push: vi.fn(),
  uploadFile: vi.fn(),
  createCandidate: vi.fn(),
  createCandidateSet: vi.fn(),
  addCandidateSetItems: vi.fn(),
}))
vi.mock('vue-router', () => ({ useRoute: () => ({ params: { id: 'task-1' }, query: {}, fullPath: '/predict-results/task-1' }), useRouter: () => ({ push }) }))
vi.mock('./molecule-table', () => ({ loadMoleculeTable }))
vi.mock('@/api/task-events', () => ({ openTaskEventStream: vi.fn() }))
vi.mock('@/api/files', () => ({ uploadFile }))
vi.mock('@/api/compounds', () => ({ createCandidate, createCandidateSet, addCandidateSetItems }))
vi.mock('@/api/tasks', () => ({ getTaskDetail: vi.fn() }))
vi.mock('ant-design-vue', () => ({ message: { success: vi.fn(), warning: vi.fn(), error: vi.fn() } }))
import PropertyPredictResult from './PropertyPredictResult.vue'

const stubs = { AppPageHeader: { template: '<div><slot name="actions" /></div>' }, TaskContextBar: true, ResultDisclaimer: true, MoleculePredictDetail: true, MetricDistributionChart: true, 'a-button': { template: '<button><slot /></button>' }, 'a-alert': true, 'a-empty': true, 'a-spin': true, 'a-card': { template: '<div><slot /><slot name="title" /><slot name="extra" /></div>' }, 'a-space': { template: '<div><slot /></div>' }, 'a-input': true, 'a-input-number': true, 'a-select': true, 'a-cascader': true, 'a-table': { props: ['columns', 'dataSource'], template: '<div data-testid="predict-result-matrix">{{ dataSource?.length }}</div>' } }

describe('PropertyPredictResult', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    loadMoleculeTable.mockResolvedValue({
      columns: [{ key: 'smiles', title: 'SMILES', originalKey: 'smiles' }, { key: 'score', title: 'Score', originalKey: 'score' }],
      rows: [{ __rowKey: 'a', smiles: 'CCO', score: '' }, { __rowKey: 'b', smiles: 'CCN', score: '0' }],
      detail: { project_id: 'p1', model_family: 'admet', tool_name: 'tool' }
    })
    uploadFile.mockResolvedValue({ data: { id: 'f-handoff-1' } })
    createCandidate.mockResolvedValue({ data: { id: 'cand-1' } })
    createCandidateSet.mockResolvedValue({ data: { id: 'set-1' } })
    addCandidateSetItems.mockResolvedValue({ data: { added: 2 } })
  })
  it('filters blank numeric cells without treating them as zero', () => {
    const rows = [{ __rowKey: 'a', smiles: 'CCO', value: '' }, { __rowKey: 'b', smiles: 'CCN', value: '0' }]
    expect(filterPredictRows(rows, { column: 'value', min: 0 }).map(row => row.__rowKey)).toEqual(['b'])
  })
  it('loads rows, saves filtered candidates, and routes screening handoff to /screen', async () => {
    const wrapper = mount(PropertyPredictResult, { global: { plugins: [i18n], stubs: { ...stubs, 'a-modal': { props: ['open'], template: '<div v-if="open" data-testid="predict-save-candidates-modal"><button @click="$emit(\'ok\')">OK</button><slot /></div>' }, 'a-form': { template: '<form><slot /></form>' }, 'a-form-item': { template: '<div><slot /></div>' } } } })
    await flushPromises()
    expect(wrapper.find('[data-testid="predict-result-page"]').exists()).toBe(true)
    expect(wrapper.get('[data-testid="predict-result-matrix"]').text()).toContain('2')
    await wrapper.get('[data-testid="predict-result-send-screening"]').trigger('click')
    await flushPromises()
    expect(push).toHaveBeenCalledWith({ name: 'ScreenConfig', query: { project_id: 'p1', file_id: 'f-handoff-1', filename: 'prediction-task-1-screening.csv' } })
  })
})
