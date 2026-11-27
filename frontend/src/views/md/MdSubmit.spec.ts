import { mount, flushPromises } from '@vue/test-utils'
import { ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import MdSubmit from './MdSubmit.vue'

const api = vi.hoisted(() => ({ listProjects: vi.fn(), listTargets: vi.fn(), getTarget: vi.fn(), getProtein: vi.fn(), getStructure: vi.fn(), listStructures: vi.fn(), findToolBySlug: vi.fn(), resolveToolVersionId: vi.fn(), submitMdTask: vi.fn(), uploadFile: vi.fn() }))
const nav = vi.hoisted(() => ({ query: {} as Record<string, unknown>, push: vi.fn() }))
vi.mock('@/api/projects', () => ({ listProjects: api.listProjects }))
vi.mock('@/api/files', () => ({ uploadFile: api.uploadFile }))
vi.mock('@/api/targets', () => ({ listTargets: api.listTargets, getTarget: api.getTarget, getProtein: api.getProtein, getStructure: api.getStructure, listStructures: api.listStructures }))
vi.mock('@/api/md', () => ({ findToolBySlug: api.findToolBySlug, resolveToolVersionId: api.resolveToolVersionId, submitMdTask: api.submitMdTask, MD_TOOL_SLUG: 'gromacs-md' }))
vi.mock('vue-router', () => ({ useRoute: () => ({ query: nav.query }), useRouter: () => ({ push: nav.push }) }))
vi.mock('vue-i18n', () => ({ useI18n: () => ({ t: (key: string) => key }) }))
vi.mock('@/composables/useModelOptions', () => ({ useModelOptions: () => ({ options: ref([{ slug: 'gromacs-md', parameterSchema: null }]), selectedSlug: ref('gromacs-md'), selectedOption: ref({ slug: 'gromacs-md', parameterSchema: null }), loading: ref(false), load: vi.fn() }) }))

const projects = [{ id: 'p1', name: 'Project' }]
const target = { id: 't1', name: 'Target', project_id: 'p1', proteins: [{ id: 'pr1', name: 'Protein', target_id: 't1' }] }
const structure = { id: 's1', protein_id: 'pr1', structure_file_id: 'file1', prepared_file_id: 'prepared1' }
function makeWrapper() { return mount(MdSubmit, { global: { stubs: { 'app-page-header': true, 'a-card': { template: '<div><slot /></div>' }, 'a-spin': { template: '<div><slot /></div>' }, 'a-empty': true, 'a-form': { template: '<form><slot /></form>' }, 'a-row': { template: '<div><slot /></div>' }, 'a-col': { template: '<div><slot /></div>' }, 'a-form-item': { template: '<div><slot /></div>' }, 'a-select': { template: '<div><slot /></div>' }, 'a-select-option': true, 'a-upload': { template: '<div><slot /></div>' }, 'a-tag': { template: '<span><slot /></span>' }, 'a-divider': true, 'a-alert': true, 'a-button': { template: '<button @click="$attrs.onClick"><slot /></button>' }, ModelSelect: true, ModelParameterForm: true } } }) }

describe('MdSubmit', () => {
  beforeEach(() => { vi.clearAllMocks(); nav.query = {}; api.listProjects.mockResolvedValue({ data: { items: projects } }); api.listTargets.mockResolvedValue({ data: { items: [{ id: 't1', name: 'Target' }] } }); api.getTarget.mockResolvedValue({ data: target }); api.getProtein.mockResolvedValue({ data: { id: 'pr1', target_id: 't1' } }); api.getStructure.mockResolvedValue({ data: structure }); api.listStructures.mockResolvedValue({ data: { items: [structure] } }); api.findToolBySlug.mockResolvedValue({ id: 'tool1' }); api.resolveToolVersionId.mockResolvedValue('version1'); api.submitMdTask.mockResolvedValue('task1'); api.uploadFile.mockResolvedValue({ data: { id: 'lig-file-1' } }) })
  it('resolves and validates partial structure ancestry before applying the cascade', async () => { nav.query = { project_id: 'p1', structure_id: 's1' }; makeWrapper(); await flushPromises(); expect(api.getStructure).toHaveBeenCalledWith('s1'); expect(api.getProtein).toHaveBeenCalledWith('pr1'); expect(api.getTarget).toHaveBeenCalledWith('t1') })
  it('uses the prepared file ID for submission', async () => { const wrapper = makeWrapper(); await flushPromises(); const vm = wrapper.vm as unknown as { form: { projectId: string; targetId: string; proteinId: string; structureId: string }; structures: typeof structure[]; handleSubmit: () => Promise<void> }; vm.form.projectId = 'p1'; vm.form.targetId = 't1'; vm.form.proteinId = 'pr1'; vm.structures = [structure]; vm.form.structureId = 's1'; await vm.handleSubmit(); expect(api.submitMdTask).toHaveBeenCalledWith(expect.objectContaining({ projectId: 'p1', complexFileId: 'prepared1', ligandFileId: null })) })
  it('uploads and submits optional ligand file ID alongside protein structure', async () => {
    const wrapper = makeWrapper()
    await flushPromises()
    const vm = wrapper.vm as unknown as { form: { projectId: string; targetId: string; proteinId: string; structureId: string }; structures: typeof structure[]; handleLigandBeforeUpload: (file: File) => Promise<boolean>; handleSubmit: () => Promise<void> }
    vm.form.projectId = 'p1'; vm.form.targetId = 't1'; vm.form.proteinId = 'pr1'; vm.structures = [structure]; vm.form.structureId = 's1'
    const ret = await vm.handleLigandBeforeUpload(new File(['M  END\n'], 'aspirin.sdf'))
    expect(ret).toBe(false)
    await vm.handleSubmit()
    expect(api.submitMdTask).toHaveBeenCalledWith(expect.objectContaining({ projectId: 'p1', complexFileId: 'prepared1', ligandFileId: 'lig-file-1' }))
  })
})
