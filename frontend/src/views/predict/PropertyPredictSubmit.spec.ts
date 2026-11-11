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

vi.mock('@/api/predict', () => ({
  submitToolTask: (...args: unknown[]) => submitToolTaskMock(...args)
}))

vi.mock('@/api/files', () => ({
  uploadFile: vi.fn().mockResolvedValue({ data: { id: 'file-uploaded' } })
}))

vi.mock('@/components/design/ModelSelect.vue', () => ({
  default: {
    name: 'ModelSelect',
    props: ['value', 'options', 'loading'],
    template: '<div class="model-select" />'
  }
}))

vi.mock('@/components/design/ModelParameterForm.vue', () => ({
  default: {
    name: 'ModelParameterForm',
    props: ['modelValue', 'schema', 'disabled'],
    template: '<div class="model-parameter-form" />'
  }
}))

vi.mock('@/composables/useModelOptions', async () => {
  const { computed, ref } = await import('vue')
  const selectedOption = computed(() => ({
    parameterSchema: null,
    inputFields: ['protein_pdb', 'ligand_sdf', 'ligand_smiles']
  }))
  return {
    useModelOptions: () => ({
      options: ref([]),
      selectedSlug: ref('tool-slug'),
      selectedOption,
      loading: ref(false),
      load: vi.fn()
    })
  }
})

import PropertyPredictSubmit from './PropertyPredictSubmit.vue'

/** `a-select` 用原生 select 替身：同时支持 `:value` + `@change` 与 `v-model:value`。 */
const ASelectStub = {
  props: ['value', 'options', 'placeholder', 'notFoundContent'],
  emits: ['update:value', 'change'],
  template: `<select class="a-select" :value="value" @change="$emit('update:value', $event.target.value); $emit('change', $event.target.value)">
    <option v-for="option in options" :key="option.value" :value="option.value">{{ option.label }}</option>
  </select>`
}

const AButtonStub = {
  props: ['disabled', 'loading', 'type', 'size'],
  emits: ['click'],
  template: '<button class="a-button" :disabled="disabled" @click="$emit(\'click\')"><slot /></button>'
}

const ARadioGroupStub = {
  props: ['value'],
  emits: ['update:value'],
  template: '<div class="radio-group"><slot /></div>'
}

function mountPage(props: Record<string, unknown> = {}) {
  return mount(PropertyPredictSubmit, {
    props,
    global: {
      stubs: {
        'a-select': ASelectStub,
        'a-button': AButtonStub,
        'a-card': { template: '<section><slot /></section>' },
        'a-radio-group': ARadioGroupStub,
        'a-radio-button': { template: '<button class="radio-button"><slot /></button>' },
        'a-upload': { template: '<div class="upload"><slot /></div>' },
        'a-checkbox-group': { template: '<div class="checkbox-group" />' },
        'a-alert': { props: ['message'], template: '<div class="alert">{{ message }}</div>' }
      }
    }
  })
}

describe('PropertyPredictSubmit', () => {
  beforeEach(() => {
    route.params = {}
    route.query = {}
    replaceMock.mockReset()
    pushMock.mockReset()
    listProjectsMock.mockResolvedValue({
      data: { items: [{ id: 'p1', name: '演示项目' }] }
    })
    listCandidateSetsMock.mockResolvedValue({
      data: { items: [{ id: 'set-1', name: '候选集 A' }] }
    })
    exportCandidateSetMock.mockResolvedValue({ data: { file_id: 'file-ligands' } })
    listTargetsMock.mockResolvedValue({ data: { items: [{ id: 't1', name: 'EGFR' }] } })
    getTargetMock.mockResolvedValue({ data: { proteins: [{ id: 'pr1', name: 'EGFR 激酶域' }] } })
    listStructuresMock.mockResolvedValue({
      data: {
        items: [
          { id: 's1', source_type: 'PREDICTED', prepared_file_id: 'file-receptor', structure_file_id: 'file-raw' }
        ]
      }
    })
    submitToolTaskMock.mockResolvedValue({ id: 'task-1' })
  })

  it('无 project_id 时给出项目选择器与明确提示，而不是静默空下拉', async () => {
    const wrapper = mountPage()
    await flushPromises()
    expect(wrapper.find('[data-testid="predict-submit-project"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('predict.submit.projectHint')
    expect(wrapper.find('[data-testid="predict-submit-button"]').attributes('disabled')).toBeDefined()
    expect(listCandidateSetsMock).not.toHaveBeenCalled()
  })

  it('选择项目后写回 URL 并加载该项目的候选集', async () => {
    const wrapper = mountPage()
    await flushPromises()
    await wrapper.find('[data-testid="predict-submit-project"]').setValue('p1')
    await flushPromises()
    expect(replaceMock).toHaveBeenCalledWith({ query: { project_id: 'p1' } })
  })

  it('带 project_id 进入时直接加载候选集与靶点', async () => {
    route.query = { project_id: 'p1' }
    mountPage()
    await flushPromises()
    expect(listCandidateSetsMock).toHaveBeenCalledWith('p1', { page: 1, page_size: 100 })
    expect(listTargetsMock).toHaveBeenCalledWith('p1', { page: 1, page_size: 100 })
  })

  it('亲和力可按项目选靶点/结构/候选集，并按产物文件 id 提交', async () => {
    route.query = { project_id: 'p1', type: 'affinity' }
    const wrapper = mountPage()
    await flushPromises()

    // 页面上有两个 radio-group：预测类型（ADMET/亲和力）与亲和力输入来源（上传/从项目选择）。
    const radioGroups = wrapper.findAllComponents(ARadioGroupStub)
    expect(radioGroups).toHaveLength(2)
    const affinitySourceGroup = radioGroups[1]
    expect(affinitySourceGroup).toBeDefined()
    affinitySourceGroup!.vm.$emit('update:value', 'project')
    await flushPromises()

    await wrapper.find('[data-testid="predict-affinity-target"]').setValue('t1')
    await flushPromises()
    await wrapper.find('[data-testid="predict-affinity-protein"]').setValue('pr1')
    await flushPromises()
    await wrapper.find('[data-testid="predict-affinity-structure"]').setValue('s1')
    await flushPromises()
    await wrapper.find('[data-testid="predict-affinity-candidateset"]').setValue('set-1')
    await flushPromises()

    expect(getTargetMock).toHaveBeenCalledWith('t1')
    expect(listStructuresMock).toHaveBeenCalledWith('pr1')

    await wrapper.find('[data-testid="predict-submit-button"]').trigger('click')
    await flushPromises()

    expect(exportCandidateSetMock).toHaveBeenCalledWith('set-1')
    expect(submitToolTaskMock).toHaveBeenCalledWith(
      expect.objectContaining({
        projectId: 'p1',
        standardInputUploads: {
          protein_pdb: 'file-receptor',
          ligand_smiles: 'file-ligands'
        }
      })
    )
  })
})
