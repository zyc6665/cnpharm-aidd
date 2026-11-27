import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { addCandidateSetItems, createCandidate, createCandidateSet } from '@/api/compounds'
import { uploadMoleculeHandoff } from '@/domain/molecules/result-handoff'
import ScreenResult from './ScreenResult.vue'

const { push, loadMoleculeTable, getTaskDetail } = vi.hoisted(() => ({ push: vi.fn(), loadMoleculeTable: vi.fn(), getTaskDetail: vi.fn() }))
vi.mock('vue-router', () => ({ useRoute: () => ({ params: { id: 'task-1' }, query: {}, fullPath: '/screening/task-1/result' }), useRouter: () => ({ push }) }))
vi.mock('vue-i18n', () => ({ useI18n: () => ({ t: (key: string, params?: object) => params ? `${key} ${JSON.stringify(params)}` : key }) }))
vi.mock('@/views/predict/molecule-table', () => ({ loadMoleculeTable }))
vi.mock('@/api/tasks', () => ({ getTaskDetail }))
vi.mock('@/api/compounds', () => ({ addCandidateSetItems: vi.fn(), createCandidate: vi.fn(), createCandidateSet: vi.fn() }))
vi.mock('@/domain/molecules/result-handoff', async importOriginal => ({
  ...await importOriginal<typeof import('@/domain/molecules/result-handoff')>(),
  uploadMoleculeHandoff: vi.fn(),
}))
vi.mock('@/api/task-events', () => ({ openTaskEventStream: vi.fn() }))
vi.mock('ant-design-vue', () => ({ message: { success: vi.fn(), warning: vi.fn(), error: vi.fn() } }))

const passthrough = { template: '<div><slot /></div>' }
const resultTableStub = {
  props: ['columns', 'dataSource', 'rowSelection'],
  template: `<div><button v-if="rowSelection" data-testid="select-mixed" @click="rowSelection.onChange(['0', '1', '2'])">Select</button>
    <div v-for="(record, index) in dataSource" :key="index">
      <slot name="bodyCell" v-for="column in columns" :key="column.key" :column="column" :record="record" />
    </div>
  </div>`,
}
const stubs = {
  AppPageHeader: { template: '<div><slot name="actions" /></div>' },
  TaskContextBar: true, ResultDisclaimer: true, FunnelChart: true,
  'a-space': passthrough,
  'a-button': { props: ['disabled'], template: '<button :disabled="disabled"><slot /></button>' },
  'a-alert': true, 'a-empty': true, 'a-row': passthrough, 'a-col': passthrough, 'a-card': passthrough,
  'a-table': resultTableStub,
  'a-statistic': true, 'a-tag': true,
  'a-modal': {
    props: ['open'], emits: ['ok'],
    template: '<div v-if="open"><slot /><button @click="$emit(\'ok\')" data-testid="confirm-save">OK</button></div>',
  },
  'a-form': passthrough, 'a-form-item': passthrough, 'a-input': true, 'a-spin': true,
}

const passed = { __rowKey: '0', rank: '1', passes: 'true', smiles: 'CCO', molecule_id: 'm1' }
const failed = { __rowKey: '1', rank: '2', passes: 'false', smiles: 'CCN', molecule_id: 'm2' }

function mockRows(rows = [passed]) {
  loadMoleculeTable.mockResolvedValue({ rows, detail: { project_id: 'p1' } })
}

function mountResult() {
  return mount(ScreenResult, { global: { stubs } })
}

const byTestId = (id: string) => `[data-testid="${id}"]`

describe('ScreenResult', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockRows()
    getTaskDetail.mockResolvedValue({ data: { id: 'task-1', project_id: 'p1' } })
  })

  it('loads results and exposes ADMET and MD handoff actions', async () => {
    getTaskDetail.mockResolvedValue({
      data: {
        id: 'task-1',
        project_id: 'p1',
        input_snapshots: [{ inputRole: 'receptor_pdb', entityType: 'protein_structure', entityId: 'struct-9', fileId: 'file-9', detail: { target_id: 'targ-9', protein_id: 'prot-9' } }]
      }
    })
    const wrapper = mountResult()
    await flushPromises()
    expect(wrapper.find(byTestId('screen-result-page')).exists()).toBe(true)
    expect(wrapper.get(byTestId('screen-send-admet')).attributes('disabled')).toBeUndefined()
    await wrapper.get(byTestId('screen-send-md')).trigger('click')
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
    const wrapper = mountResult()
    await flushPromises()
    await wrapper.get(byTestId('screen-send-md')).trigger('click')
    await flushPromises()
    expect(push).toHaveBeenCalledWith({ path: '/md', query: { project_id: 'p1' } })
  })

  it('blocks candidate save and ADMET when all positive-ranked rows fail', async () => {
    mockRows([{ ...passed, passes: 'false' }, failed])
    const wrapper = mountResult()
    await flushPromises()

    expect(wrapper.find(byTestId('screen-zero-pass-alert')).exists()).toBe(true)
    expect(wrapper.get(byTestId('screen-save-candidates')).attributes('disabled')).toBeDefined()
    expect(wrapper.get(byTestId('screen-send-admet')).attributes('disabled')).toBeDefined()
    expect(wrapper.get(byTestId('screen-result-export')).attributes('disabled')).toBeUndefined()
    expect(wrapper.get(byTestId('screen-send-md')).attributes('disabled')).toBeUndefined()
  })

  it('saves and sends only selected rows with a passing result and valid SMILES', async () => {
    mockRows([passed, failed, { ...passed, __rowKey: '2', smiles: 'N/A' }, { ...passed, __rowKey: '3', smiles: 'CCC' }])
    vi.mocked(createCandidate).mockResolvedValue({ data: { id: 'c1' } } as never)
    vi.mocked(createCandidateSet).mockResolvedValue({ data: { id: 'cs1' } } as never)
    vi.mocked(uploadMoleculeHandoff).mockResolvedValue({ file_id: 'f1', filename: 'screening-task-1-admet.csv' })
    const wrapper = mountResult()
    await flushPromises()
    await wrapper.get(byTestId('select-mixed')).trigger('click')

    await wrapper.get(byTestId('screen-save-candidates')).trigger('click')
    expect(wrapper.get(byTestId('screen-save-candidates-modal')).text()).toContain('screening.result.saveSelectedScope {"count":1,"total":3}')
    await wrapper.get(byTestId('confirm-save')).trigger('click')
    await flushPromises()
    expect(createCandidate).toHaveBeenCalledTimes(1)
    expect(createCandidate).toHaveBeenCalledWith('p1', expect.objectContaining({ smiles: 'CCO' }))
    expect(addCandidateSetItems).toHaveBeenCalledWith('cs1', { candidate_ids: ['c1'] })

    await wrapper.get(byTestId('screen-send-admet')).trigger('click')
    await flushPromises()
    expect(uploadMoleculeHandoff).toHaveBeenCalledExactlyOnceWith([{ smiles: 'CCO', moleculeId: 'm1' }], 'screening-task-1-admet.csv')
  })

  it('offers a pose button only for passing rows with a positive integer rank', async () => {
    mockRows([passed, failed, { ...passed, __rowKey: '2', rank: '0' }])
    const wrapper = mountResult()
    await flushPromises()

    expect(wrapper.get(byTestId('screen-result-table')).text().match(/screening\.result\.poseNotExported/g)).toHaveLength(2)
    const buttons = wrapper.findAll(byTestId('screen-view-pose'))
    expect(buttons).toHaveLength(1)
    expect(buttons[0]!.element.tagName).toBe('BUTTON')
    await buttons[0]!.trigger('click')
    expect(push).toHaveBeenCalledWith({ path: '/docking-results/pose-1', query: { task_id: 'task-1' } })
  })

  it('recognizes "t" truthy flag identically to funnel logic', async () => {
    mockRows([{ ...passed, passes: 't' }])
    const wrapper = mountResult()
    await flushPromises()

    expect(wrapper.find(byTestId('screen-zero-pass-alert')).exists()).toBe(false)
    expect(wrapper.get(byTestId('screen-save-candidates')).attributes('disabled')).toBeUndefined()
    expect(wrapper.findAll(byTestId('screen-view-pose'))).toHaveLength(1)
  })
})
