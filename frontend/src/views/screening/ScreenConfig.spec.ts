import { defineComponent } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const route = { params: {} as Record<string, string>, query: {} as Record<string, string> }
const replaceMock = vi.fn()
const pushMock = vi.fn()

const listProjectsMock = vi.fn()
const listCandidateSetsMock = vi.fn()
const exportCandidateSetMock = vi.fn()
const listTargetsMock = vi.fn()
const getTargetMock = vi.fn()
const listStructuresMock = vi.fn()
const submitToolTaskMock = vi.fn()
const uploadFileMock = vi.fn()

vi.mock('vue-router', () => ({
  useRoute: () => route,
  useRouter: () => ({ replace: replaceMock, push: pushMock })
}))

vi.mock('vue-i18n', () => ({
  useI18n: () => ({ t: (key: string) => key })
}))

vi.mock('ant-design-vue', () => ({
  message: { success: vi.fn(), error: vi.fn(), warning: vi.fn() }
}))

vi.mock('@/api/projects', () => ({
  listProjects: (...args: unknown[]) => listProjectsMock(...args)
}))

vi.mock('@/api/compounds', () => ({
  listCandidateSets: (...args: unknown[]) => listCandidateSetsMock(...args),
  exportCandidateSet: (...args: unknown[]) => exportCandidateSetMock(...args)
}))

vi.mock('@/api/targets', () => ({
  listTargets: (...args: unknown[]) => listTargetsMock(...args),
  getTarget: (...args: unknown[]) => getTargetMock(...args),
  listStructures: (...args: unknown[]) => listStructuresMock(...args)
}))

vi.mock('@/api/screening', () => ({
  submitToolTask: (...args: unknown[]) => submitToolTaskMock(...args)
}))

vi.mock('@/api/files', () => ({
  uploadFile: (...args: unknown[]) => uploadFileMock(...args)
}))

vi.mock('@/components/design/ModelSelect.vue', () => ({
  default: {
    name: 'ModelSelect',
    props: ['modelValue', 'options', 'loading'],
    emits: ['update:modelValue'],
    template: '<div class="model-select" />'
  }
}))

const mockModelState = vi.hoisted(() => ({
  selectedSlugRef: null as { value: string } | null,
  selectedOptionRef: null as { value: unknown } | null
}))

vi.mock('@/composables/useModelOptions', async () => {
  const { ref } = await import('vue')
  mockModelState.selectedSlugRef = ref('autodock-vina-docking')
  mockModelState.selectedOptionRef = ref(null)
  return {
    useModelOptions: () => ({
      options: ref([]),
      selectedSlug: mockModelState.selectedSlugRef,
      selectedOption: mockModelState.selectedOptionRef,
      loading: ref(false),
      load: vi.fn()
    })
  }
})

import ScreenConfig from './ScreenConfig.vue'

const ASelectStub = {
  props: ['value', 'options', 'placeholder', 'disabled', 'notFoundContent'],
  emits: ['update:value', 'change'],
  template: `<select class="a-select" :value="value" :disabled="disabled" @change="$emit('update:value', $event.target.value); $emit('change', $event.target.value)">
    <option v-for="option in options" :key="option.value" :value="option.value">{{ option.label }}</option>
  </select>`
}

const AButtonStub = {
  props: ['disabled', 'loading', 'type', 'size'],
  emits: ['click'],
  template: '<button class="a-button" :disabled="disabled" @click="$emit(\'click\', $event)"><slot /></button>'
}

const ARadioGroupStub = {
  props: ['value'],
  emits: ['update:value'],
  template: '<div class="radio-group"><slot /></div>'
}

const AUploadStub = defineComponent({
  name: 'AUploadStub',
  props: ['beforeUpload', 'accept', 'maxCount', 'multiple', 'fileList'],
  template: '<div class="upload"><slot /></div>'
})

const AInputStub = {
  props: ['value', 'status', 'disabled', 'placeholder'],
  emits: ['update:value'],
  template: '<input :value="value" :disabled="disabled" @input="$emit(\'update:value\', $event.target.value)" />'
}

const AInputNumberStub = {
  props: ['value', 'min', 'max', 'step', 'precision', 'placeholder'],
  emits: ['update:value'],
  template: `<input type="number" class="number" :value="value ?? ''"
    @input="$emit('update:value', $event.target.value === '' ? null : Number($event.target.value))" />`
}

function mountPage(props: Record<string, unknown> = {}) {
  return mount(ScreenConfig, {
    props,
    global: {
      stubs: {
        'a-select': ASelectStub,
        'a-button': AButtonStub,
        'a-card': { props: ['title'], template: '<section><slot /></section>' },
        'a-form': { template: '<form><slot /></form>' },
        'a-form-item': { props: ['label'], template: '<div><slot /></div>' },
        'a-radio-group': ARadioGroupStub,
        'a-radio-button': { template: '<button class="radio-button"><slot /></button>' },
        'a-upload': AUploadStub,
        'a-input': AInputStub,
        'a-input-number': AInputNumberStub,
        'a-tag': { template: '<span class="tag"><slot /></span>' },
        'a-alert': { props: ['message'], template: '<div class="alert">{{ message }}</div>' },
        'a-row': { template: '<div><slot /></div>' },
        'a-col': { template: '<div><slot /></div>' },
        ModelParameterForm: { props: ['modelValue', 'schema', 'overrides', 'primaryKeys', 'disabled'], template: '<div data-testid="lddm-param-form" />' },
        FragmentSketchModal: {
          name: 'FragmentSketchModal',
          props: ['open', 'molecule', 'selectedIndices', 'mode'],
          emits: ['update:open', 'confirm'],
          template: '<div v-if="open" data-testid="dock-sketch-modal" />'
        }
      }
    }
  })
}

describe('ScreenConfig input sources', () => {
  beforeEach(() => {
    route.params = {}
    route.query = {}
    if (mockModelState.selectedSlugRef) mockModelState.selectedSlugRef.value = 'autodock-vina-docking'
    if (mockModelState.selectedOptionRef) mockModelState.selectedOptionRef.value = null
    replaceMock.mockReset()
    pushMock.mockReset()
    uploadFileMock.mockReset()
    uploadFileMock.mockResolvedValue({ data: { id: 'file-uploaded' } })
    submitToolTaskMock.mockReset()
    listCandidateSetsMock.mockReset()
    exportCandidateSetMock.mockReset()
    listTargetsMock.mockReset()
    getTargetMock.mockReset()
    listStructuresMock.mockReset()
    submitToolTaskMock.mockReset()
    listProjectsMock.mockResolvedValue({ data: { items: [{ id: 'p1', name: '演示项目' }, { id: 'proj-a', name: '项目 A' }, { id: 'proj-b', name: '项目 B' }] } })
    listCandidateSetsMock.mockResolvedValue({
      data: { items: [{ id: 'set-1', name: '候选集 A', item_count: 21 }] }
    })
    exportCandidateSetMock.mockResolvedValue({ data: { file_id: 'file-ligands', row_count: 21 } })
    listTargetsMock.mockResolvedValue({ data: { items: [{ id: 't1', name: 'EGFR' }] } })
    getTargetMock.mockResolvedValue({ data: { proteins: [{ id: 'pr1', name: 'EGFR 激酶域' }] } })
    listStructuresMock.mockResolvedValue({
      data: {
        items: [
          {
            id: 's1',
            source_type: 'PREDICTED',
            prepared_file_id: 'file-receptor',
            structure_file_id: 'file-raw',
            created_at: '2026-11-11T02:35:59.094453Z'
          }
        ]
      }
    })
    submitToolTaskMock.mockResolvedValue({ id: 'task-1' })
  })

  it('没有 project_id 时给出项目选择器，而不是一个空的项目来源', async () => {
    const wrapper = mountPage()
    await flushPromises()
    expect(wrapper.find('[data-testid="screen-config-project"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('screening.config.projectHint')
    // 项目来源的靶点/蛋白/结构下拉此时禁用（没有项目就没有可选资产）
    expect(listTargetsMock).not.toHaveBeenCalled()
  })

  it('选择项目后写回 URL 参数并加载该项目的靶点与候选集', async () => {
    const wrapper = mountPage()
    await flushPromises()
    await wrapper.find('[data-testid="screen-config-project-select"]').setValue('p1')
    await flushPromises()
    expect(replaceMock).toHaveBeenCalledWith({ query: { project_id: 'p1' } })
  })

  it('带 project_id 进入时加载靶点与候选集', async () => {
    route.query = { project_id: 'p1' }
    mountPage()
    await flushPromises()
    expect(listTargetsMock).toHaveBeenCalledWith('p1', { page: 1, page_size: 100 })
    expect(listCandidateSetsMock).toHaveBeenCalledWith('p1', { page: 1, page_size: 100 })
  })

  it('受体与配体都可以从项目选，提交时不重复上传文件', async () => {
    route.query = { project_id: 'p1' }
    const wrapper = mountPage()
    await flushPromises()

    const groups = wrapper.findAllComponents(ARadioGroupStub)
    expect(groups).toHaveLength(2)
    groups[0]!.vm.$emit('update:value', 'project')
    groups[1]!.vm.$emit('update:value', 'candidate')
    await flushPromises()

    await wrapper.find('[data-testid="screen-config-target"]').setValue('t1')
    await flushPromises()
    await wrapper.find('[data-testid="screen-config-protein"]').setValue('pr1')
    await flushPromises()
    await wrapper.find('[data-testid="screen-config-structure"]').setValue('s1')
    await flushPromises()
    await wrapper.find('[data-testid="screen-config-candidate-set"]').setValue('set-1')
    await flushPromises()

    expect(getTargetMock).toHaveBeenCalledWith('t1')
    expect(listStructuresMock).toHaveBeenCalledWith('pr1')

    await wrapper.find('[data-testid="screen-config-submit"]').trigger('click')
    await flushPromises()

    expect(uploadFileMock).not.toHaveBeenCalled()
    expect(exportCandidateSetMock).toHaveBeenCalledWith('set-1')
    expect(submitToolTaskMock).toHaveBeenCalledTimes(1)
    const payload = submitToolTaskMock.mock.calls[0]![0] as {
      projectId: string
      standardInputUploads: Record<string, string>
    }
    expect(payload.projectId).toBe('p1')
    // 结构用产物文件 id（prepared_file_id 优先），配体用候选集导出的 file_id
    expect(payload.standardInputUploads.protein_pdb).toBe('file-receptor')
    expect(payload.standardInputUploads.ligand_smiles).toBe('file-ligands')
    expect(pushMock).toHaveBeenCalledWith('/tasks/task-1/screening')
  })

  it('项目里没有可选结构时禁用提交并给出原因', async () => {
    route.query = { project_id: 'p1' }
    listStructuresMock.mockResolvedValue({ data: { items: [] } })
    const wrapper = mountPage()
    await flushPromises()

    const groups = wrapper.findAllComponents(ARadioGroupStub)
    groups[0]!.vm.$emit('update:value', 'project')
    await flushPromises()

    await wrapper.find('[data-testid="screen-config-target"]').setValue('t1')
    await flushPromises()

    expect(wrapper.text()).toContain('screening.config.noStructures')
    expect(
      wrapper.find('[data-testid="screen-config-submit"]').attributes('disabled')
    ).toBeDefined()
  })

  it('project switch clears upstream ligand handoff and candidate mode', async () => {
    route.query = { project_id: 'proj-a', file_id: 'file-a', filename: 'a.csv' }
    const wrapper = mountPage()
    await flushPromises()
    expect(wrapper.find('[data-testid="screen-config-preuploaded-ligands"]').exists()).toBe(true)

    const groups = wrapper.findAllComponents(ARadioGroupStub)
    groups[1]!.vm.$emit('update:value', 'candidate')
    await flushPromises()
    exportCandidateSetMock.mockClear()
    submitToolTaskMock.mockClear()
    await wrapper.find('[data-testid="screen-config-project-select"]').setValue('proj-b')
    await flushPromises()

    expect(replaceMock).toHaveBeenCalledWith({ query: { project_id: 'proj-b' } })
    expect(wrapper.find('[data-testid="screen-config-preuploaded-ligands"]').exists()).toBe(false)
    expect(exportCandidateSetMock).not.toHaveBeenCalled()
    expect(submitToolTaskMock).not.toHaveBeenCalled()
  })

  it('上游 candidate_set_id 交接：直接切到候选集模式并选中', async () => {
    route.query = { project_id: 'p1', candidate_set_id: 'set-1' }
    const wrapper = mountPage()
    await flushPromises()

    const candidateSelect = wrapper.find('[data-testid="screen-config-candidate-set"]')
    expect(candidateSelect.exists()).toBe(true)
    expect((candidateSelect.element as HTMLSelectElement).value).toBe('set-1')
  })

  it('上游 file_id 交接：upload 模式下展示已落盘配体并直接复用', async () => {
    route.query = {
      project_id: 'p1',
      file_id: 'file-generated-ligands',
      filename: 'generated_molecules.csv'
    }
    const wrapper = mountPage()
    await flushPromises()

    const badge = wrapper.find('[data-testid="screen-config-preuploaded-ligands"]')
    expect(badge.exists()).toBe(true)
    expect(badge.text()).toContain('generated_molecules.csv')

    const groups = wrapper.findAllComponents(ARadioGroupStub)
    groups[0]!.vm.$emit('update:value', 'project')
    await flushPromises()
    await wrapper.find('[data-testid="screen-config-target"]').setValue('t1')
    await flushPromises()
    await wrapper.find('[data-testid="screen-config-protein"]').setValue('pr1')
    await flushPromises()
    await wrapper.find('[data-testid="screen-config-structure"]').setValue('s1')
    await flushPromises()

    await wrapper.find('[data-testid="screen-config-submit"]').trigger('click')
    await flushPromises()

    expect(uploadFileMock).not.toHaveBeenCalled()
    const payload = submitToolTaskMock.mock.calls[0]![0] as {
      standardInputUploads: Record<string, string>
    }
    expect(payload.standardInputUploads.protein_pdb).toBe('file-receptor')
    expect(payload.standardInputUploads.ligand_smiles).toBe('file-generated-ligands')
    expect(pushMock).toHaveBeenCalledWith('/tasks/task-1/screening')
  })

  it('supports LDDM pocket & partial docking with sketch selection and ref_ligand submission', async () => {
    mockModelState.selectedSlugRef!.value = 'lddm-pocket-ligand-generation'
    mockModelState.selectedOptionRef!.value = {
      slug: 'lddm-pocket-ligand-generation',
      name: 'LDDM 口袋条件分子生成',
      isDefault: false,
      inputFields: ['protein_pdb', 'fragment_sdf'],
      inputSlots: ['protein_pdb', 'pocket', 'fragment_sdf', 'ref_ligand'],
      parameterSchema: {
        type: 'object',
        properties: {
          generation_mode: { type: 'string', enum: ['denovo', 'fragment', 'dock'], default: 'denovo' },
          n_samples: { type: 'integer', default: 10 },
          n_steps: { type: 'integer', default: 100 },
          atoms_to_dock: { type: 'string', default: '' },
          molecule_size: { type: 'string', default: '' },
          center_x: { type: 'number' },
          center_y: { type: 'number' },
          center_z: { type: 'number' }
        }
      }
    }

    const wrapper = mountPage()
    await flushPromises()

    expect(wrapper.find('[data-testid="screen-dock-ligand-section"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="screen-config-rules"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="screen-dock-summary"]').exists()).toBe(true)

    const makeTextFile = (name: string, text: string) => {
      const file = new File([text], name)
      Object.defineProperty(file, 'text', { value: vi.fn().mockResolvedValue(text) })
      return file
    }

    const molBlock = [
      'Methanol', '  Test', '', '  2  1  0  0  0  0            999 V2000',
      '    1.0000    2.0000    3.0000 C   0  0  0  0  0  0  0  0  0  0  0  0',
      '    3.0000    6.0000    9.0000 O   0  0  0  0  0  0  0  0  0  0  0  0',
      '  1  2  1  0  0  0  0', 'M  END'
    ].join('\n')

    const receptorUpload = wrapper.findAllComponents(AUploadStub).find(w => w.attributes('data-testid') === 'screen-config-receptor-upload')!
    const ligandUpload = wrapper.findAllComponents(AUploadStub).find(w => w.attributes('data-testid') === 'screen-dock-ligand-upload')!
    const refLigandUpload = wrapper.findAllComponents(AUploadStub).find(w => w.attributes('data-testid') === 'screen-dock-ref-ligand-upload')!

    const receptorFile = makeTextFile('receptor.pdb', 'ATOM      1  CA  GLY A   1      1.000  2.000  3.000  1.00  0.00           C\nEND\n')
    const ligandMol = makeTextFile('ligand.mol', molBlock)
    const refSdf = makeTextFile('ref.sdf', `${molBlock}\n$$$$\n`)

    await (receptorUpload.props('beforeUpload') as (f: File) => Promise<boolean>)(receptorFile)
    await (ligandUpload.props('beforeUpload') as (f: File) => Promise<boolean>)(ligandMol)
    await (refLigandUpload.props('beforeUpload') as (f: File) => Promise<boolean>)(refSdf)
    await flushPromises()

    expect(wrapper.find('[data-testid="screen-dock-ref-ligand-summary"]').exists()).toBe(true)

    // Partial-dock validation & sketcher confirm
    const atomsInput = wrapper.find('[data-testid="screen-dock-atoms-input"]')
    await atomsInput.setValue('2')
    await flushPromises()
    expect(wrapper.find('[data-testid="screen-config-submit"]').attributes('disabled')).toBeDefined()

    await wrapper.find('[data-testid="open-fragment-sketch"]').trigger('click')
    await flushPromises()
    wrapper.findComponent({ name: 'FragmentSketchModal' }).vm.$emit('confirm', { selectedIndices: [0, 1], exportedFile: null })
    await flushPromises()
    expect((atomsInput.element as HTMLInputElement).value).toBe('0 1')

    await wrapper.find('[data-testid="screen-config-submit"]').trigger('click')
    await flushPromises()

    expect(uploadFileMock).toHaveBeenCalledTimes(3)
    expect(submitToolTaskMock).toHaveBeenCalledWith(expect.objectContaining({
      toolSlug: 'lddm-pocket-ligand-generation',
      params: expect.objectContaining({
        generation_mode: 'dock',
        atoms_to_dock: '0 1',
        n_samples: 10,
        n_steps: 100,
        center_x: 2,
        center_y: 4,
        center_z: 6
      }),
      standardInputUploads: {
        protein_pdb: 'file-uploaded',
        fragment_sdf: 'file-uploaded',
        ref_ligand: 'file-uploaded'
      }
    }))
    expect(pushMock).toHaveBeenCalledWith('/tasks/task-1/results')
  })

  it('uploads pocket artifact in pocket_file mode and blocks partial docking for V3000 or multi-record SDFs', async () => {
    mockModelState.selectedSlugRef!.value = 'lddm-pocket-ligand-generation'
    mockModelState.selectedOptionRef!.value = {
      slug: 'lddm-pocket-ligand-generation',
      name: 'LDDM 口袋条件分子生成',
      isDefault: false,
      inputFields: ['protein_pdb', 'fragment_sdf'],
      inputSlots: ['protein_pdb', 'pocket', 'fragment_sdf', 'ref_ligand'],
      parameterSchema: {
        type: 'object',
        properties: {
          generation_mode: { type: 'string', enum: ['denovo', 'fragment', 'dock'], default: 'denovo' },
          n_samples: { type: 'integer', default: 10 }
        }
      }
    }

    const wrapper = mountPage()
    await flushPromises()

    const makeTextFile = (name: string, text: string) => {
      const file = new File([text], name)
      Object.defineProperty(file, 'text', { value: vi.fn().mockResolvedValue(text) })
      return file
    }

    const receptorUpload = wrapper.findAllComponents(AUploadStub).find(w => w.attributes('data-testid') === 'screen-config-receptor-upload')!
    const ligandUpload = wrapper.findAllComponents(AUploadStub).find(w => w.attributes('data-testid') === 'screen-dock-ligand-upload')!
    const receptorFile = makeTextFile('receptor.pdb', 'ATOM      1  CA  GLY A   1      1.000  2.000  3.000  1.00  0.00           C\nEND\n')
    await (receptorUpload.props('beforeUpload') as (f: File) => Promise<boolean>)(receptorFile)

    // Multi-record SDF should be rejected for single-ligand LDDM docking
    const multiSdf = makeTextFile('multi.sdf', 'mol1\n$$$$\nmol2\n$$$$\n')
    await (ligandUpload.props('beforeUpload') as (f: File) => Promise<boolean>)(multiSdf)
    await flushPromises()
    expect(wrapper.text()).toContain('screening.config.dockLigandSingleOnly')
    expect(wrapper.find('[data-testid="screen-config-submit"]').attributes('disabled')).toBeDefined()

    // V3000 SDF keeps atomCount null: full docking allowed, partial atoms_to_dock rejected
    const v3000Sdf = makeTextFile('v3000.sdf', 'V3000\n  test\n\n  0  0  0     0  0            999 V3000\nM  V30 BEGIN CTAB\nM  END\n$$$$\n')
    await (ligandUpload.props('beforeUpload') as (f: File) => Promise<boolean>)(v3000Sdf)
    await flushPromises()

    wrapper.findComponent({ name: 'PocketCoordinatePanel' }).vm.$emit('update:modelValue', 'pocket_file')
    await flushPromises()
    const pocketUpload = wrapper.findAllComponents(AUploadStub).find(w => w.attributes('data-testid') === 'screen-dock-pocket-upload')!
    const pocketFile = makeTextFile('pocket0.pdb', 'HETATM    1  C1  UNL A   1       4.000   5.000   6.000  1.00  0.00           C\nEND\n')
    await (pocketUpload.props('beforeUpload') as (f: File) => Promise<boolean>)(pocketFile)
    await flushPromises()

    // Non-empty atoms_to_dock on V3000 cannot be range-checked -> blocked
    const atomsInput = wrapper.find('[data-testid="screen-dock-atoms-input"]')
    await atomsInput.setValue('999')
    await flushPromises()
    expect(wrapper.text()).toContain('design.molecule.atomsToDockUnverifiable')
    expect(wrapper.find('[data-testid="screen-config-submit"]').attributes('disabled')).toBeDefined()

    // Clear atoms_to_dock -> full-ligand dock submits with uploads.pocket
    await atomsInput.setValue('')
    await flushPromises()
    await wrapper.find('[data-testid="screen-config-submit"]').trigger('click')
    await flushPromises()

    expect(uploadFileMock).toHaveBeenCalledTimes(3)
    expect(submitToolTaskMock).toHaveBeenCalledWith(expect.objectContaining({
      standardInputUploads: {
        protein_pdb: 'file-uploaded',
        fragment_sdf: 'file-uploaded',
        pocket: 'file-uploaded'
      }
    }))
  })
})
