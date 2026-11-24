import { beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import i18n from '@/locales'

const { push } = vi.hoisted(() => ({ push: vi.fn() }))

vi.mock('vue-router', () => ({
  useRoute: () => ({ params: { id: 'task-1' }, fullPath: '/design/results/task-1' }),
  useRouter: () => ({ push }),
}))

vi.mock('@/api/design', () => ({
  getDesignGenerationResult: vi.fn(),
  findMoleculeTableArtifact: vi.fn(),
  loadDesignTable: vi.fn(),
}))

vi.mock('@/api/task-events', () => ({
  openTaskEventStream: vi.fn(() => ({ available: true, close: vi.fn() })),
}))

vi.mock('@/api/tasks', () => ({
  getTaskDetail: vi.fn().mockRejectedValue(new Error('no task detail in unit test')),
  isTaskTerminalStatus: (status: string) =>
    ['success', 'failure', 'timeout', 'canceled', 'rejected'].includes(status),
}))

vi.mock('@/api/compounds', () => ({
  createCandidate: vi.fn(),
  createCandidateSet: vi.fn(),
  addCandidateSetItems: vi.fn(),
}))

vi.mock('@/utils/protected-file-access', () => ({
  fetchProtectedFileText: vi.fn(),
  saveBlobAsFile: vi.fn(),
}))

vi.mock('ant-design-vue', () => ({
  message: { success: vi.fn(), warning: vi.fn(), error: vi.fn() },
}))

vi.mock('@ant-design/icons-vue', () => ({
  CopyOutlined: { template: '<span class="copy-icon" />' },
}))

import { getDesignGenerationResult, findMoleculeTableArtifact, loadDesignTable } from '@/api/design'
import GenerationResults from './GenerationResults.vue'
import type { DesignTable } from '@/types/design'

const t = i18n.global.t

const smilesOnlyTable: DesignTable = {
  columns: [{ key: 'smiles', title: 'smiles', numeric: false }],
  rows: [
    { __rowKey: '0', smiles: 'CCO' },
    { __rowKey: '1', smiles: 'CCN' },
  ],
}

const fullTable: DesignTable = {
  columns: [
    { key: 'smiles', title: 'smiles', numeric: false },
    { key: 'score', title: 'score', numeric: true },
    { key: 'mw', title: 'mw', numeric: true },
    { key: 'logp', title: 'logp', numeric: true },
    { key: 'hbd', title: 'hbd', numeric: true },
    { key: 'hba', title: 'hba', numeric: true },
    { key: 'tpsa', title: 'tpsa', numeric: true },
    { key: 'qed', title: 'qed', numeric: true },
  ],
  rows: [
    {
      __rowKey: '0',
      smiles: 'CC(=O)Oc1ccccc1C(=O)O',
      score: '0.91',
      mw: '780',
      logp: '2.1',
      hbd: '1',
      hba: '3',
      tpsa: '80',
      qed: '0.42',
    },
    {
      __rowKey: '1',
      smiles: 'CCN(CC)CC',
      score: '0.75',
      mw: '320',
      logp: '1.2',
      // 缺氢键供体：Lipinski 该条必须显示「未计算」，不能算「符合」。
      hbd: '',
      hba: '2',
      tpsa: '60',
      qed: '0.8',
    },
  ],
}

const stubs = {
  AppPageHeader: { template: '<div><slot name="actions" /></div>' },
  TaskContextBar: true,
  ResultDisclaimer: true,
  Smiles2DCell: { props: ['smiles'], template: '<div class="smiles-stub" />' },
  MoleculeViewer: true,
  DruglikenessRadar: {
    props: ['properties', 'size'],
    template: '<div data-testid="druglikeness-radar" />',
  },
  'a-button': { template: '<button><slot /></button>' },
  'a-alert': {
    props: ['message', 'description'],
    template:
      '<div class="a-alert"><span class="a-alert__message">{{ message }}</span><span class="a-alert__desc">{{ description }}</span><slot name="action" /></div>',
  },
  'a-select': {
    props: ['value'],
    emits: ['update:value'],
    template:
      '<select :value="value" @change="$emit(\'update:value\', $event.target.value)"><slot /></select>',
  },
  'a-select-option': { props: ['value'], template: '<option :value="value"><slot /></option>' },
  'a-radio-group': { template: '<div><slot /></div>' },
  'a-radio-button': { template: '<button><slot /></button>' },
  'a-input-number': {
    props: ['value'],
    emits: ['update:value'],
    template:
      '<input type="number" :value="value" @input="$emit(\'update:value\', $event.target.value)" />',
  },
  'a-input': {
    props: ['value'],
    emits: ['update:value'],
    template:
      '<input :value="value" @input="$emit(\'update:value\', $event.target.value)" />',
  },
  'a-checkbox': {
    props: ['checked', 'indeterminate'],
    emits: ['change'],
    template:
      '<label class="a-checkbox"><input type="checkbox" :checked="checked" @change="$emit(\'change\', $event)" /><slot /></label>',
  },
  'a-segmented': {
    props: ['value', 'options'],
    emits: ['update:value'],
    template:
      '<div class="a-segmented"><button v-for="opt in options" :key="opt.value" :data-value="opt.value" @click="$emit(\'update:value\', opt.value)">{{ opt.label }}</button></div>',
  },
  'a-rate': { props: ['value', 'disabled'], template: '<span class="a-rate" :data-value="value" />' },
  'a-tag': { props: ['color'], template: '<span class="a-tag" :data-color="color"><slot /></span>' },
  'a-slider': { template: '<div class="a-slider" />' },
  'a-pagination': true,
  'a-modal': { props: ['open'], template: '<div v-if="open"><slot /></div>' },
  'a-form': { template: '<form><slot /></form>' },
  'a-form-item': { template: '<div><slot /></div>' },
}

async function mountResults(): Promise<ReturnType<typeof mount>> {
  const wrapper = mount(GenerationResults, {
    global: { plugins: [i18n], stubs },
  })
  await flushPromises()
  return wrapper
}

function mockTable(table: DesignTable): void {
  vi.mocked(findMoleculeTableArtifact).mockReturnValue({
    artifactId: 'a1',
    versionId: 'v1',
    semanticType: null,
    standardType: null,
    filename: null,
  } as never)
  vi.mocked(loadDesignTable).mockResolvedValue(table as never)
}

describe('GenerationResults', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    push.mockReset()
    vi.mocked(getDesignGenerationResult).mockResolvedValue({
      status: 'success',
      project_id: 'p1',
      outputs: [],
    } as never)
    mockTable(smilesOnlyTable)
  })

  describe('SMILES-only results', () => {
    it('defaults to the compact table with no sort dropdown and no radar charts in the list', async () => {
      const wrapper = await mountResults()

      expect(wrapper.find('[data-testid="molecule-table"]').exists()).toBe(true)
      expect(wrapper.find('[data-testid="molecule-grid"]').exists()).toBe(false)
      expect(wrapper.findAll('[data-testid="molecule-row"]')).toHaveLength(2)
      expect(wrapper.find('[data-testid="results-sort-key"]').exists()).toBe(false)
      expect(wrapper.findAll('[data-testid="druglikeness-radar"]')).toHaveLength(0)
      expect(wrapper.find('.col-druglikeness').exists()).toBe(false)
    })

    it('never renders a fake green Lipinski tag and explains where properties come from', async () => {
      const wrapper = await mountResults()

      expect(wrapper.find('[data-testid="results-property-guidance"]').exists()).toBe(true)
      expect(wrapper.text()).toContain(t('design.results.noPropertyData.description'))
      expect(wrapper.find('[data-testid="results-goto-predict"]').exists()).toBe(true)
      expect(wrapper.find('.a-tag').exists()).toBe(false)
      expect(wrapper.text()).not.toContain(t('design.results.lipinskiPass'))
    })

    it('shows the selected molecule SMILES in the sticky viewer', async () => {
      const wrapper = await mountResults()

      expect(wrapper.find('[data-testid="viewer-smiles"]').text()).toContain('CCO')
      expect(wrapper.text()).toContain(t('design.results.moleculeIndex', { index: 1 }))
    })

    it('navigates to property prediction with the project id', async () => {
      const wrapper = await mountResults()

      await wrapper.get('[data-testid="results-goto-predict"]').trigger('click')

      expect(push).toHaveBeenCalledWith({ name: 'PropertyPredict', query: { project_id: 'p1' } })
    })
  })

  describe('full property results', () => {
    beforeEach(() => mockTable(fullTable))

    it('renders numeric columns, the sort dropdown and range sliders', async () => {
      const wrapper = await mountResults()

      expect(wrapper.find('[data-testid="results-sort-key"]').exists()).toBe(true)
      expect(wrapper.get('[data-testid="molecule-table"]').text()).toContain('mw')
      expect(wrapper.get('[data-testid="molecule-table"]').text()).toContain('qed')
      expect(wrapper.find('[data-testid="results-mw-range"]').exists()).toBe(true)
      expect(wrapper.find('[data-testid="results-logp-range"]').exists()).toBe(true)
      expect(wrapper.find('[data-testid="results-property-guidance"]').exists()).toBe(false)
    })

    it('clicking a row updates the viewer and renders exactly one radar chart', async () => {
      const wrapper = await mountResults()

      await wrapper.findAll('[data-testid="molecule-row"]')[1]!.trigger('click')
      await flushPromises()

      expect(wrapper.find('[data-testid="viewer-smiles"]').text()).toContain('CCN(CC)CC')
      expect(wrapper.text()).toContain(t('design.results.moleculeIndex', { index: 2 }))
      expect(wrapper.findAll('[data-testid="druglikeness-radar"]')).toHaveLength(1)
      expect(wrapper.find('[data-testid="results-viewer-rating"]').exists()).toBe(true)
    })

    it('renders empty numeric cells as "-" and never as "0"', async () => {
      mockTable({
        columns: [
          { key: 'smiles', title: 'smiles', numeric: false },
          { key: 'score', title: 'score', numeric: true },
        ],
        rows: [
          { __rowKey: '0', smiles: 'CCO', score: '' },
          { __rowKey: '1', smiles: 'CCN', score: '0.5' },
        ],
      })
      const wrapper = await mountResults()

      const numericCells = wrapper
        .findAll('[data-testid="molecule-table"] td.col-num')
        .map(cell => cell.text().trim())
      expect(numericCells).toEqual(['0.5', '-'])
      expect(numericCells).not.toContain('0')

      await wrapper.get('[data-value="card"]').trigger('click')
      await flushPromises()

      const cardMetrics = wrapper
        .findAll('.molecule-card__metric dd')
        .map(cell => cell.text().trim())
      expect(cardMetrics).toContain('-')
      expect(cardMetrics).not.toContain('0')
    })

    it('marks passing, violating and missing Lipinski rules correctly', async () => {
      const wrapper = await mountResults()

      // 第一行：MW 780 越界，其余有值。
      const violation = wrapper.findAll('.a-tag[data-color="error"]')
      expect(violation.length).toBeGreaterThan(0)
      expect(wrapper.text()).toContain(t('design.results.lipinskiFail'))
      expect(wrapper.findAll('.a-tag[data-color="success"]').length).toBeGreaterThan(0)

      // 第二行：hbd 缺失 → 中性「未计算」，绝不能是绿色「符合」。
      await wrapper.findAll('[data-testid="molecule-row"]')[1]!.trigger('click')
      await flushPromises()

      const neutral = wrapper.findAll('.a-tag[data-color="default"]')
      expect(neutral).toHaveLength(1)
      expect(neutral[0]!.text()).toBe(t('design.results.lipinskiUnknown'))
      expect(neutral[0]!.text()).not.toBe(t('design.results.lipinskiPass'))
    })
  })

  describe('search, view toggle and batch selection', () => {
    it('filters rows by SMILES keyword', async () => {
      const wrapper = await mountResults()

      await wrapper.get('[data-testid="results-search-input"]').setValue('CCN')
      await flushPromises()

      expect(wrapper.findAll('[data-testid="molecule-row"]')).toHaveLength(1)
      expect(wrapper.get('[data-testid="molecule-table"]').text()).toContain('CCN')
      expect(wrapper.get('[data-testid="molecule-table"]').text()).not.toContain('CCO')
    })

    it('switches between table and card views without radar charts on cards', async () => {
      const wrapper = await mountResults()

      await wrapper.get('[data-value="card"]').trigger('click')
      await flushPromises()

      expect(wrapper.find('[data-testid="molecule-grid"]').exists()).toBe(true)
      expect(wrapper.find('[data-testid="molecule-table"]').exists()).toBe(false)
      expect(wrapper.findAll('[data-testid="molecule-card"]')).toHaveLength(2)
      expect(wrapper.findAll('[data-testid="druglikeness-radar"]')).toHaveLength(0)
      expect(wrapper.find('[data-testid="molecule-card-rating"]').exists()).toBe(false)

      await wrapper.get('[data-value="table"]').trigger('click')
      await flushPromises()
      expect(wrapper.find('[data-testid="molecule-table"]').exists()).toBe(true)
    })

    it('opens the save modal for selected rows', async () => {
      const wrapper = await mountResults()

      await wrapper.findAll('[data-testid="molecule-row"]')[0]!.find('input[type="checkbox"]').setValue(true)
      await flushPromises()

      expect(wrapper.find('[data-testid="results-batch-bar"]').exists()).toBe(true)
      expect(wrapper.text()).toContain(t('design.results.selectedCount', { count: 1 }))

      await wrapper.get('[data-testid="results-save-selected"]').trigger('click')
      await flushPromises()

      expect(wrapper.find('[data-testid="results-save-modal"]').exists()).toBe(true)
      expect(wrapper.find('[data-testid="results-set-name"]').exists()).toBe(true)
    })
  })

  describe('non-success terminal statuses', () => {
    it.each(['timeout', 'rejected'] as const)(
      'treats %s tasks as failures and blocks saving',
      async (terminalStatus) => {
        vi.mocked(getDesignGenerationResult).mockResolvedValue({
          status: terminalStatus,
          project_id: 'p1',
          outputs: [],
        } as never)

        const wrapper = await mountResults()

        expect(wrapper.find('[data-testid="results-task-failed"]').exists()).toBe(true)
        expect(wrapper.find('[data-testid="results-summary"]').exists()).toBe(false)
        expect(wrapper.find('[data-testid="molecule-table"]').exists()).toBe(false)
        expect(wrapper.find('[data-testid="molecule-grid"]').exists()).toBe(false)

        const saveButton = wrapper.get('[data-testid="results-save-set"]')
        expect(saveButton.attributes('disabled')).toBeDefined()
      }
    )
  })
})
