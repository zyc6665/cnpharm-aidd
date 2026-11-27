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

vi.mock('@/api/files', () => ({
  uploadFile: vi.fn(),
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
  StarFilled: { template: '<span class="star-filled" />' },
  StarOutlined: { template: '<span class="star-outlined" />' },
  StopOutlined: { template: '<span class="stop-outlined" />' },
}))

import { message } from 'ant-design-vue'
import { getDesignGenerationResult, findMoleculeTableArtifact, loadDesignTable } from '@/api/design'
import { uploadFile } from '@/api/files'
import { getTaskDetail } from '@/api/tasks'
import { fetchProtectedFileText, saveBlobAsFile } from '@/utils/protected-file-access'
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
  MoleculeViewer: { name: 'MoleculeViewer', props: ['scene', 'mode'], template: '<div />' },
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
    emits: ['change', 'update:checked'],
    template:
      '<label class="a-checkbox"><input type="checkbox" :checked="checked" @change="$emit(\'change\', $event); $emit(\'update:checked\', $event.target.checked)" /><slot /></label>',
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
  'a-popover': { template: '<div class="a-popover"><slot name="content" /><slot /></div>' },
  'a-tooltip': {
    props: ['title'],
    template: '<span class="a-tooltip" :data-tooltip="title"><slot /></span>',
  },
  MoleculeCompareDrawer: {
    props: ['open', 'molecules'],
    template:
      '<div v-if="open" data-testid="molecule-compare-drawer"><span v-for="m in molecules" :key="m.key" data-testid="molecule-compare-column" :data-index="m.index">{{ m.smiles }}</span></div>',
  },
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
    window.localStorage.clear()
    vi.mocked(getTaskDetail).mockRejectedValue(new Error('no task detail in unit test'))
    vi.mocked(getDesignGenerationResult).mockResolvedValue({
      status: 'success',
      project_id: 'p1',
      outputs: [],
    } as never)
    mockTable(smilesOnlyTable)
  })

  describe('LDDM standard artifacts', () => {
    const ligandUrl = '/api/v1/artifacts/ligands/versions/v1/files/structure_file/download'
    const sdfRecord = (name: string) => `${name}\n  LDDM\n\n  0  0  0  0  0  0  0  0  0  0999 V2000\nM  END\n$$$$\n`
    const scoredTable: DesignTable = {
      columns: ['smiles', 'mol_index', 'sa_score', 'qed', 'logp', 'mw', 'score'].map(key => ({
        key, title: key, numeric: key !== 'smiles',
      })),
      rows: [
        { __rowKey: '0', smiles: 'CCO', mol_index: '1', sa_score: '1.5', qed: '0.45', logp: '0.2', mw: '46', score: '0.5' },
        { __rowKey: '1', smiles: 'CCN', mol_index: '3', sa_score: '1.2', qed: '0.42', logp: '0.1', mw: '45', score: '0.7' },
      ],
    }

    beforeEach(() => {
      mockTable(scoredTable)
      vi.mocked(getDesignGenerationResult).mockResolvedValue({
        status: 'success',
        project_id: 'p1',
        tool_slug: 'lddm-pocket-ligand-generation',
        outputs: [
          { id: 'molecules', version_id: 'v1', semantic_type: 'molecule_table@1', filename: 'molecules.csv' },
          { id: 'report', version_id: 'v1', semantic_type: 'run_report@1', filename: 'report.json' },
          { id: 'ligands', version_id: 'v1', semantic_type: 'ligand_structure@1', filename: 'ligands.sdf' },
        ],
      } as never)
      vi.mocked(getTaskDetail).mockResolvedValue({
        data: {
          input_snapshots: [{
            inputRole: 'RECEPTOR', fileId: 'receptor', detail: { slot: 'protein_pdb', filename: 'protein.pdb' },
          }],
        },
      } as never)
      vi.mocked(fetchProtectedFileText).mockResolvedValue(sdfRecord('pose 1') + sdfRecord('pose 3'))
    })

    it('previews and exports the selected LDDM pose after sorting by the generation score', async () => {
      const wrapper = await mountResults()

      expect(wrapper.get('[data-testid="viewer-smiles"]').text()).toContain('CCN')
      expect(wrapper.get('[data-testid="molecule-table"]').text()).toContain('sa_score')
      const viewer = wrapper.getComponent({ name: 'MoleculeViewer' })
      expect(viewer.props('mode')).toBe('docking')
      expect(viewer.props('scene').entries).toEqual([
        expect.objectContaining({ role: 'receptor', url: '/api/v1/files/receptor/download' }),
        expect.objectContaining({ role: 'ligand', url: ligandUrl, sdfRecordIndex: 1 }),
      ])

      await wrapper.get('[data-testid="molecule-row"] input[type="checkbox"]').setValue(true)
      await wrapper.get('[data-testid="results-export-sdf"]').trigger('click')
      await flushPromises()

      expect(fetchProtectedFileText).toHaveBeenCalledExactlyOnceWith(ligandUrl)
      expect(saveBlobAsFile).toHaveBeenCalledWith(sdfRecord('pose 3'), 'molecules-task-1.sdf', 'chemical/x-mdl-sdfile')
    })

    it('shows the 2D structure when the artifact record count disagrees with the table', async () => {
      vi.mocked(fetchProtectedFileText).mockResolvedValue(sdfRecord('pose 1'))
      const wrapper = await mountResults()

      const fallback = wrapper.get('[data-testid="results-viewer-fallback"]')
      expect(fallback.find('.smiles-stub').exists()).toBe(true)
      expect(fallback.text()).toContain(t('design.results.noMatching3d'))
      expect(wrapper.findComponent({ name: 'MoleculeViewer' }).exists()).toBe(false)
    })

    it('matches a tagged artifact pose when the CSV has no model indices', async () => {
      mockTable(smilesOnlyTable)
      const taggedPose = sdfRecord('pose 1').replace('$$$$', '> <SMILES>\nCCO\n\n$$$$')
      vi.mocked(fetchProtectedFileText).mockResolvedValue(taggedPose)
      const wrapper = await mountResults()

      expect(wrapper.getComponent({ name: 'MoleculeViewer' }).props('scene').entries[1]).toEqual(
        expect.objectContaining({ url: ligandUrl, sdfRecordIndex: 0 })
      )
    })

    it('opens a fresh molecule generation form in the result project', async () => {
      const wrapper = await mountResults()
      await wrapper.get('[data-testid="results-new-generation"]').trigger('click')

      expect(push).toHaveBeenCalledWith({ name: 'MoleculeGeneration', query: { project_id: 'p1' } })
    })
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

  describe('DrugFlow-style review tools', () => {
    beforeEach(() => mockTable(fullTable))

    it('tones numeric cells by druggability thresholds and explains headers', async () => {
      const wrapper = await mountResults()

      const firstRowTones = wrapper
        .findAll('[data-testid="molecule-row"]')[0]!
        .findAll('td.col-num .metric-value')
        .map(cell => cell.attributes('data-tone'))

      // 列顺序：score, mw, logp, hbd, hba, tpsa, qed
      expect(firstRowTones).toEqual([undefined, 'bad', 'good', 'good', 'good', 'good', 'warn'])

      const secondRowTones = wrapper
        .findAll('[data-testid="molecule-row"]')[1]!
        .findAll('td.col-num .metric-value')
        .map(cell => cell.attributes('data-tone'))
      // 缺值（hbd = ''）必须保持中性，不能染成绿色。
      expect(secondRowTones[3]).toBeUndefined()

      const tooltips = wrapper.findAll('.a-tooltip').map(node => node.attributes('data-tooltip'))
      expect(tooltips).toContain(t('design.results.thresholds.mw.hint'))
      expect(tooltips).toContain(t('design.results.thresholds.qed.hint'))
    })

    it('hides columns through the column toggle', async () => {
      const wrapper = await mountResults()

      expect(wrapper.get('[data-testid="molecule-table"]').text()).toContain('mw')

      await wrapper.get('[data-testid="results-column-option-mw"] input').setValue(false)
      await flushPromises()

      expect(wrapper.get('[data-testid="molecule-table"]').text()).not.toContain('mw')
      expect(wrapper.get('[data-testid="molecule-table"]').text()).toContain('qed')
    })

    it('persists favorite / excluded marks and filters by them', async () => {
      const wrapper = await mountResults()

      await wrapper.findAll('[data-testid="molecule-row-favorite"]')[0]!.trigger('click')
      await wrapper.findAll('[data-testid="molecule-row-exclude"]')[1]!.trigger('click')
      await flushPromises()

      const stored = JSON.parse(
        window.localStorage.getItem('design:results:marks:v2:task-1') ?? '{}'
      ) as { favorite?: string[]; excluded?: string[] }
      expect(stored.favorite).toEqual(['smiles:CC(=O)Oc1ccccc1C(=O)O'])
      expect(stored.excluded).toEqual(['smiles:CCN(CC)CC'])

      await wrapper.get('[data-testid="results-mark-filter"] [data-value="favorite"]').trigger('click')
      await flushPromises()
      expect(wrapper.findAll('[data-testid="molecule-row"]')).toHaveLength(1)

      await wrapper.get('[data-testid="results-mark-filter"] [data-value="hideExcluded"]').trigger('click')
      await flushPromises()
      expect(wrapper.findAll('[data-testid="molecule-row"]')).toHaveLength(1)
      expect(wrapper.get('[data-testid="molecule-table"]').text()).not.toContain('CCN(CC)CC')

      // 重新挂载后标记从 localStorage 恢复。
      const remounted = await mountResults()
      expect(remounted.findAll('[data-testid="molecule-row"]')[0]!.classes()).toContain('is-favorite')
    })

    it('steps the sticky viewer with prev / next', async () => {
      const wrapper = await mountResults()

      expect(wrapper.get('[data-testid="viewer-prev"]').attributes('disabled')).toBeDefined()
      expect(wrapper.get('[data-testid="viewer-smiles"]').text()).toContain('CC(=O)Oc1ccccc1C(=O)O')

      await wrapper.get('[data-testid="viewer-next"]').trigger('click')
      await flushPromises()

      expect(wrapper.get('[data-testid="viewer-smiles"]').text()).toContain('CCN(CC)CC')
      expect(wrapper.get('[data-testid="viewer-next"]').attributes('disabled')).toBeDefined()

      await wrapper.get('[data-testid="viewer-prev"]').trigger('click')
      await flushPromises()

      expect(wrapper.get('[data-testid="viewer-smiles"]').text()).toContain('CC(=O)Oc1ccccc1C(=O)O')
    })

    it('only renders scaffold controls when the table really has a scaffold column', async () => {
      const withoutScaffold = await mountResults()
      expect(withoutScaffold.find('[data-testid="results-scaffold-filter-row"]').exists()).toBe(false)

      mockTable({
        columns: [
          { key: 'smiles', title: 'smiles', numeric: false },
          { key: 'scaffold', title: 'scaffold', numeric: false },
          { key: 'mw', title: 'mw', numeric: true },
        ],
        rows: [
          { __rowKey: '0', smiles: 'CCO', scaffold: 'c1ccccc1', mw: '120' },
          { __rowKey: '1', smiles: 'CCN', scaffold: 'c1ccncc1', mw: '90' },
        ],
      })
      const withScaffold = await mountResults()

      expect(withScaffold.find('[data-testid="results-scaffold-filter-row"]').exists()).toBe(true)
      expect(withScaffold.get('[data-testid="molecule-table"]').text()).toContain('c1ccccc1')
      expect(withScaffold.get('[data-testid="results-scaffold-filter"]').text()).toContain('c1ccccc1')
    })
  })

  describe('downstream pipeline handoff', () => {
    it('uploads the selected molecules as CSV and opens ADMET prediction', async () => {
      vi.mocked(uploadFile).mockResolvedValue({ data: { id: 'file-9' } } as never)
      const wrapper = await mountResults()

      await wrapper.get('[data-testid="results-handoff"] [data-testid="results-send-admet"]').trigger('click')
      await flushPromises()

      expect(uploadFile).toHaveBeenCalledTimes(1)
      const file = vi.mocked(uploadFile).mock.calls[0]![0] as File
      expect(file.name).toContain('admet')
      expect(file.name.endsWith('.csv')).toBe(true)
      expect(push).toHaveBeenCalledWith({
        name: 'PropertyPredict',
        query: { project_id: 'p1', file_id: 'file-9', filename: file.name },
      })
    })

    it('uploads a CSV and opens the screening setup for the screening handoff', async () => {
      vi.mocked(uploadFile).mockResolvedValue({ data: { id: 'file-10' } } as never)
      const wrapper = await mountResults()

      await wrapper.get('[data-testid="results-send-screening"]').trigger('click')
      await flushPromises()

      expect(push).toHaveBeenCalledWith({
        name: 'ScreenConfig',
        query: {
          project_id: 'p1',
          file_id: 'file-10',
          filename: expect.stringContaining('screening') as unknown as string,
        },
      })
    })

    it('warns instead of navigating when the upload fails', async () => {
      vi.mocked(uploadFile).mockRejectedValue(new Error('upload down'))
      const wrapper = await mountResults()

      await wrapper.get('[data-testid="results-send-admet"]').trigger('click')
      await flushPromises()

      expect(push).not.toHaveBeenCalled()
      expect(message.error).toHaveBeenCalledWith(t('design.results.handoff.failed'))
    })

    it('warns explicitly when SDF export finds no confirmed 3D matches for active rows', async () => {
      const { saveBlobAsFile } = await import('@/utils/protected-file-access')
      const wrapper = await mountResults()

      await wrapper.findAll('[data-testid="molecule-row"]')[0]!.find('input[type="checkbox"]').setValue(true)
      await flushPromises()
      await wrapper.get('[data-testid="results-export-sdf"]').trigger('click')
      await flushPromises()

      expect(saveBlobAsFile).not.toHaveBeenCalled()
      expect(message.warning).toHaveBeenCalledWith(
        t('design.results.exportSdfUnconfirmed', { count: 1 })
      )
    })
  })

  describe('multi-molecule comparison', () => {
    it('opens the compare drawer with the selected molecules', async () => {
      mockTable(fullTable)
      const wrapper = await mountResults()
      const rows = wrapper.findAll('[data-testid="molecule-row"]')

      await rows[0]!.find('input[type="checkbox"]').setValue(true)
      await rows[1]!.find('input[type="checkbox"]').setValue(true)
      await flushPromises()

      expect(wrapper.get('[data-testid="results-compare-btn"]').attributes('disabled')).toBeUndefined()

      await wrapper.get('[data-testid="results-compare-btn"]').trigger('click')
      await flushPromises()

      const columns = wrapper.findAll('[data-testid="molecule-compare-column"]')
      expect(columns).toHaveLength(2)
      expect(columns[0]!.text()).toContain('CC(=O)Oc1ccccc1C(=O)O')
      expect(columns[1]!.text()).toContain('CCN(CC)CC')
    })

    it('keeps the compare button disabled for a single selection', async () => {
      mockTable(fullTable)
      const wrapper = await mountResults()

      await wrapper
        .findAll('[data-testid="molecule-row"]')[0]!
        .find('input[type="checkbox"]')
        .setValue(true)
      await flushPromises()

      expect(wrapper.get('[data-testid="results-compare-btn"]').attributes('disabled')).toBeDefined()
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

  describe('Round 4 review improvements', () => {
    it('sorts vina_score ascending (most negative first) and shows Ro5 violation tags instead of stars', async () => {
      mockTable({
        columns: [
          { key: 'smiles', title: 'smiles', numeric: false },
          { key: 'vina_score', title: 'vina_score', numeric: true },
          { key: 'mw', title: 'mw', numeric: true },
          { key: 'logp', title: 'logp', numeric: true },
          { key: 'hbd', title: 'hbd', numeric: true },
          { key: 'hba', title: 'hba', numeric: true },
          { key: 'tpsa', title: 'tpsa', numeric: true },
        ],
        rows: [
          { __rowKey: '0', smiles: 'CCO', vina_score: '-6.1', mw: '180', logp: '1.2', hbd: '1', hba: '3', tpsa: '60' },
          { __rowKey: '1', smiles: 'CCN', vina_score: '-10.5', mw: '620', logp: '6.1', hbd: '1', hba: '4', tpsa: '70' },
        ],
      })
      const wrapper = await mountResults()

      // Most negative vina_score (-10.5) should appear first
      const firstCells = wrapper.findAll('[data-testid="molecule-row"]')[0]!.findAll('td.col-num')
      expect(firstCells[0]!.text()).toBe('-10.5')
      expect(wrapper.get('[data-testid="results-viewer-rating"]').text()).toBe(
        t('design.results.ro5ViolationsBadge', { count: 2 })
      )
      expect(wrapper.text()).toContain(t('design.results.lowerIsBetter'))
    })

    it('applies Ro5 preset, reports missing-value exclusions, and updates handoff counts dynamically', async () => {
      mockTable(fullTable)
      const wrapper = await mountResults()

      expect(wrapper.get('[data-testid="results-handoff"] [data-testid="results-send-admet"]').text()).toBe(
        t('design.results.handoff.sendAdmetCount', { count: 2 })
      )

      await wrapper.get('[data-testid="results-ro5-preset"]').trigger('click')
      await flushPromises()

      // Row 0 (MW 780) is filtered by MW<=500, Row 1 (hbd='') is excluded due to missing hbd
      expect(wrapper.findAll('[data-testid="molecule-row"]')).toHaveLength(0)
      expect(wrapper.get('[data-testid="results-missing-excluded"]').text()).toBe(
        t('design.results.missingExcludedNotice', { count: 1 }).trim()
      )

      await wrapper.get('[data-testid="results-include-missing-toggle"] input').setValue(true)
      await flushPromises()

      expect(wrapper.findAll('[data-testid="molecule-row"]')).toHaveLength(1)
      expect(wrapper.find('[data-testid="results-missing-excluded"]').exists()).toBe(false)
      expect(wrapper.get('[data-testid="results-handoff"] [data-testid="results-send-admet"]').text()).toBe(
        t('design.results.handoff.sendAdmetCount', { count: 1 })
      )
    })

    it('disables Ro5 preset without druglikeness columns and scopes preset to existing columns', async () => {
      mockTable({
        columns: [
          { key: 'smiles', title: 'smiles', numeric: false },
          { key: 'score', title: 'score', numeric: true },
        ],
        rows: [
          { __rowKey: '0', smiles: 'CCO', score: '-8.2' },
          { __rowKey: '1', smiles: 'CCN', score: '-7.5' },
        ],
      })
      const wrapperNoRo5 = await mountResults()
      const ro5Btn = wrapperNoRo5.get('[data-testid="results-ro5-preset"]')
      expect(ro5Btn.attributes('disabled')).toBeDefined()
      await ro5Btn.trigger('click')
      await flushPromises()
      expect(wrapperNoRo5.findAll('[data-testid="molecule-row"]')).toHaveLength(2)

      // Partial Ro5 columns: only mw exists — Ro5 preset should not filter out rows on missing hbd/hba/logp
      mockTable({
        columns: [
          { key: 'smiles', title: 'smiles', numeric: false },
          { key: 'mw', title: 'mw', numeric: true },
        ],
        rows: [
          { __rowKey: '0', smiles: 'CCO', mw: '320' },
          { __rowKey: '1', smiles: 'CCN', mw: '780' },
        ],
      })
      const wrapperPartial = await mountResults()
      const partialBtn = wrapperPartial.get('[data-testid="results-ro5-preset"]')
      expect(partialBtn.attributes('disabled')).toBeUndefined()
      await partialBtn.trigger('click')
      await flushPromises()
      expect(wrapperPartial.findAll('[data-testid="molecule-row"]')).toHaveLength(1)
    })

    it('respects include-missing toggle when filtering by QED min', async () => {
      mockTable({
        columns: [
          { key: 'smiles', title: 'smiles', numeric: false },
          { key: 'qed', title: 'qed', numeric: true },
        ],
        rows: [
          { __rowKey: '0', smiles: 'CCO', qed: '0.8' },
          { __rowKey: '1', smiles: 'CCN', qed: '' },
          { __rowKey: '2', smiles: 'CCC', qed: '0.3' },
        ],
      })
      const wrapper = await mountResults()

      await wrapper.get('[data-testid="results-toggle-filters"]').trigger('click')
      await wrapper.get('[data-testid="results-qed-min"]').setValue('0.5')
      await flushPromises()

      expect(wrapper.findAll('[data-testid="molecule-row"]')).toHaveLength(1)
      expect(wrapper.get('[data-testid="results-missing-excluded"]').text()).toBe(
        t('design.results.missingExcludedNotice', { count: 1 }).trim()
      )

      await wrapper.get('[data-testid="results-include-missing-toggle"] input').setValue(true)
      await flushPromises()

      expect(wrapper.findAll('[data-testid="molecule-row"]')).toHaveLength(2)
      expect(wrapper.find('[data-testid="results-missing-excluded"]').exists()).toBe(false)
    })

    it('displays queue position and estimated wait in results-progress when task is pending', async () => {
      vi.mocked(getDesignGenerationResult).mockResolvedValue({
        status: 'pending',
        project_id: 'p1',
        outputs: [],
      } as never)
      vi.mocked(getTaskDetail).mockResolvedValue({
        data: {
          status: 'queued',
          dispatch: { queue: 'gpu_queue', queue_position: 3, estimated_wait_seconds: 120 },
        },
      } as never)

      const wrapper = await mountResults()
      const progressBox = wrapper.get('[data-testid="results-progress"]')
      expect(progressBox.text()).toContain(t('design.progressCard.queuePosition', { position: 3 }))
      expect(progressBox.text()).toContain('2')
    })
  })
})
