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
    props: ['value', 'options', 'loading'],
    template: '<div class="model-select" />'
  }
}))

vi.mock('@/composables/useModelOptions', async () => {
  const { ref } = await import('vue')
  return {
    useModelOptions: () => ({
      options: ref([]),
      selectedSlug: ref('autodock-vina-docking'),
      selectedOption: ref(null),
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
  template: '<button class="a-button" :disabled="disabled" @click="$emit(\'click\')"><slot /></button>'
}

const ARadioGroupStub = {
  props: ['value'],
  emits: ['update:value'],
  template: '<div class="radio-group"><slot /></div>'
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
        'a-upload': { template: '<div class="upload"><slot /></div>' },
        'a-input-number': { props: ['value'], template: '<input class="number" />' },
        'a-tag': { template: '<span class="tag"><slot /></span>' },
        'a-alert': { props: ['message'], template: '<div class="alert">{{ message }}</div>' },
        'a-row': { template: '<div><slot /></div>' },
        'a-col': { template: '<div><slot /></div>' }
      }
    }
  })
}

describe('ScreenConfig input sources', () => {
  beforeEach(() => {
    route.params = {}
    route.query = {}
    replaceMock.mockReset()
    pushMock.mockReset()
    uploadFileMock.mockReset()
    uploadFileMock.mockResolvedValue({ data: { id: 'file-uploaded' } })
    listProjectsMock.mockResolvedValue({ data: { items: [{ id: 'p1', name: '演示项目' }] } })
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
})
