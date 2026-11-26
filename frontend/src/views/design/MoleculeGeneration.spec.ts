import { defineComponent } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import MoleculeGeneration from './MoleculeGeneration.vue'

const POCKET2MOL = 'pocket2mol-pocket-ligand-generation'
const LDDM = 'lddm-pocket-ligand-generation'
const mocks = vi.hoisted(() => ({
  listTools: vi.fn(),
  listProjects: vi.fn(),
  resolve: vi.fn(),
  submit: vi.fn(),
  upload: vi.fn()
}))

vi.mock('vue-i18n', () => ({
  useI18n: () => ({
    t: (key: string, values?: Record<string, number | string>) =>
      values && 'count' in values ? `${key}:${values.count}:${values.lastIndex}` : key,
    te: () => false
  })
}))
vi.mock('vue-router', () => ({ useRoute: () => ({ query: {} }), useRouter: () => ({ push: vi.fn() }) }))
vi.mock('ant-design-vue', () => ({ message: { warning: vi.fn(), success: vi.fn(), error: vi.fn() } }))
vi.mock('@/api/tools', () => ({ getToolList: mocks.listTools }))
vi.mock('@/api/design', () => ({ resolveToolBySlug: mocks.resolve, submitDesignTask: mocks.submit }))
vi.mock('@/api/files', () => ({ uploadFile: mocks.upload }))
vi.mock('@/api/artifacts', () => ({ uploadProjectArtifact: vi.fn() }))
vi.mock('@/api/projects', () => ({ listProjects: mocks.listProjects }))

const pocket = {
  projectId: 'project', structureFileId: 'protein', pocketLabel: 'Pocket 1',
  center: { x: 1, y: 2, z: 3 }
}

const ModelSelect = defineComponent({
  props: ['modelValue', 'options', 'disabled'],
  emits: ['update:modelValue'],
  template: `<select data-testid="model" :value="modelValue" :disabled="disabled"
    @change="$emit('update:modelValue', $event.target.value)">
    <option v-for="option in options" :key="option.slug" :value="option.slug">{{ option.name }}</option>
  </select>`
})
const PocketPicker = defineComponent({
  emits: ['update:modelValue'],
  setup() { return { pocket } },
  template: '<button data-testid="pick-pocket" @click="$emit(\'update:modelValue\', pocket)">Pick</button>'
})
const ParameterForm = defineComponent({
  props: ['modelValue', 'schema', 'overrides', 'primaryKeys', 'disabled'],
  template: '<div />'
})
const RadioGroup = defineComponent({
  props: ['value', 'disabled'],
  emits: ['update:value'],
  template: '<fieldset :disabled="disabled" :data-value="value" @click="$emit(\'update:value\', $event.target.value)"><slot /></fieldset>'
})
const RadioButton = defineComponent({ props: ['value'], template: '<button :value="value"><slot /></button>' })
const Upload = defineComponent({ props: ['beforeUpload', 'disabled'], template: '<div><slot /></div>' })
const Button = defineComponent({ props: ['type', 'disabled', 'loading'], template: '<button :disabled="disabled || loading" :data-variant="type"><slot /></button>' })
const Input = defineComponent({
  props: ['value', 'status', 'disabled'],
  emits: ['update:value'],
  template: '<input :value="value" :disabled="disabled" @input="$emit(\'update:value\', $event.target.value)" />'
})
const Alert = defineComponent({ props: ['message', 'type'], template: '<div>{{ message }}</div>' })

const molBlock = [
  'Methanol', '  Test', '', '  2  1  0  0  0  0            999 V2000',
  '    0.0000    0.0000    0.0000 C   0  0  0  0  0  0  0  0  0  0  0  0',
  '    1.4000    0.0000    0.0000 O   0  0  0  0  0  0  0  0  0  0  0  0',
  '  1  2  1  0  0  0  0', 'M  END'
].join('\r\n')

function structureFile(name: string, text: string): File {
  const file = new File([text], name)
  // jsdom's File does not expose Blob.text() on all supported versions.
  Object.defineProperty(file, 'text', { value: vi.fn().mockResolvedValue(text) })
  return file
}

function model(slug: string, properties: Record<string, object>) {
  return { slug, status: 'published', name: slug, contract: { schema: { input: { type: 'object', properties } } } }
}

function mountPage() {
  return mount(MoleculeGeneration, {
    global: {
      stubs: {
        PocketPicker, ModelSelect, AppPageHeader: true, ModelParameterForm: ParameterForm,
        ParameterPresets: true, TaskProgressCard: true, 'a-alert': Alert, 'a-radio-button': RadioButton,
        'a-radio-group': RadioGroup, 'a-select': true, 'a-button': Button, 'a-upload': Upload,
        'a-input': Input, 'a-descriptions-item': true, 'a-descriptions': true,
        'a-tag': { props: ['color'], template: '<span><slot /></span>' },
        'a-modal': { props: ['open', 'title'], emits: ['update:open'], template: '<div v-if="open" data-testid="sketch-modal-stub"><slot /><slot name="footer" /></div>' },
        MoleculeViewer: { props: ['scene', 'voxelGrid'], template: '<div data-testid="context-viewer" />' },
        'a-spin': defineComponent({ template: '<div><slot /></div>' })
      }
    }
  })
}

const byId = (id: string) => `[data-testid="${id}"]`
let wrapper: ReturnType<typeof mountPage>
const get = (id: string) => wrapper.get(byId(id))
const submit = () => get('molecule-submit')
const blocked = () => submit().attributes('disabled') !== undefined
const hidden = (id: string) => !wrapper.find(byId(id)).exists()

async function selectModel(slug: string) {
  await get('model').setValue(slug)
  await flushPromises()
}

async function chooseFragment(file: File) {
  const { beforeUpload } = wrapper.getComponent(Upload).props()
  expect(await beforeUpload(file)).toBe(false)
  await flushPromises()
}

beforeEach(async () => {
  localStorage.clear()
  vi.resetAllMocks()
  mocks.listTools.mockResolvedValue({ data: { items: [
    model(POCKET2MOL, { num_samples: { type: 'integer', default: 20 } }),
    model(LDDM, {
      generation_mode: { type: 'string', enum: ['denovo', 'fragment', 'dock'], default: 'denovo' },
      n_samples: { type: 'integer', default: 10 },
      n_steps: { type: 'integer', default: 100 },
      molecule_size: { type: 'string', default: '' },
      atoms_to_dock: { type: 'string', default: '' }
    })
  ] } })
  mocks.listProjects.mockResolvedValue({ data: { items: [{ id: 'project', name: 'Demo Project' }] } })
  mocks.resolve.mockImplementation(async slug => ({ tool: { id: slug }, version: { id: `${slug}-v1` } }))
  mocks.submit.mockResolvedValue({ data: { id: 'task' } })
  mocks.upload.mockResolvedValue({ data: { id: 'ligand' } })
  wrapper = mountPage()
  await flushPromises()
  await get('pick-pocket').trigger('click')
})

afterEach(() => wrapper.unmount())

describe('MoleculeGeneration', () => {
  it('discovers LDDM and switches schemas without leaking fragment state into Pocket2Mol', async () => {
    expect(hidden('molecule-generation-modes')).toBe(true)
    expect(wrapper.getComponent(ParameterForm).props('modelValue')).toMatchObject({ num_samples: 20 })
    await selectModel(LDDM)
    expect(get('molecule-generation-modes').get('fieldset').attributes('data-value')).toBe('denovo')
    expect(wrapper.getComponent(ParameterForm).props('overrides')).toMatchObject({
      generation_mode: { hidden: true }, atoms_to_dock: { hidden: true }
    })
    await get('molecule-mode-fragment').trigger('click')
    await chooseFragment(structureFile('ligand.sdf', `${molBlock}\r\n$$$$\r\n`))
    await selectModel(POCKET2MOL)
    expect(hidden('molecule-generation-modes')).toBe(true)
    expect(hidden('molecule-fragment-section')).toBe(true)
    await submit().trigger('click')
    await flushPromises()
    expect(mocks.upload).not.toHaveBeenCalled()
    expect(mocks.submit).toHaveBeenCalledWith(expect.objectContaining({
      toolId: POCKET2MOL,
      params: { num_samples: 20, center_x: 1, center_y: 2, center_z: 3 },
      standardInputUploads: { protein_pdb: 'protein' }
    }))
    await selectModel(LDDM)
    await get('molecule-mode-fragment').trigger('click')
    expect(hidden('molecule-fragment-name')).toBe(true)
    expect(blocked()).toBe(true)
  })

  it('requires ligand files for both modes and clears the alert on de novo or reset', async () => {
    await selectModel(LDDM)
    for (const mode of ['fragment', 'dock']) {
      await get(`molecule-mode-${mode}`).trigger('click')
      expect(get('molecule-fragment-required').text()).toBe('design.molecule.fragmentRequired')
      expect(blocked()).toBe(true)
      await submit().trigger('click')
    }
    expect(mocks.submit).not.toHaveBeenCalled()
    await get('molecule-mode-denovo').trigger('click')
    expect(hidden('molecule-fragment-required')).toBe(true)
    expect(blocked()).toBe(false)
    await get('molecule-mode-fragment').trigger('click')
    await get('molecule-reset-params').trigger('click')
    expect(hidden('molecule-fragment-section')).toBe(true)
    await submit().trigger('click')
    await flushPromises()
    expect(mocks.upload).not.toHaveBeenCalled()
    expect(mocks.submit).toHaveBeenCalledWith(expect.objectContaining({
      toolId: LDDM,
      params: { generation_mode: 'denovo', n_samples: 10, n_steps: 100, center_x: 1, center_y: 2, center_z: 3 },
      standardInputUploads: { protein_pdb: 'protein' }
    }))
  })

  it('previews a V2000 SDF and submits the fragment with the selected size preset', async () => {
    await selectModel(LDDM)
    await get('molecule-mode-fragment').trigger('click')
    const ligand = structureFile('ligand.sdf', `${molBlock}\r\n$$$$\r\n`)
    await chooseFragment(ligand)
    expect(get('molecule-fragment-preview').text()).toBe('design.molecule.fragmentAtomCount:2:1')
    expect(get('molecule-size-auto').attributes('data-variant')).toBe('primary')
    await get('molecule-size-small').trigger('click')
    expect(get('molecule-size-small').attributes('data-variant')).toBe('primary')
    await get('molecule-size-auto').trigger('click')
    expect(wrapper.getComponent(ParameterForm).props('modelValue').molecule_size).toBe('')
    await get('molecule-size-medium').trigger('click')
    await submit().trigger('click')
    await flushPromises()
    expect(mocks.upload).toHaveBeenCalledExactlyOnceWith(ligand)
    expect(mocks.submit).toHaveBeenCalledWith(expect.objectContaining({
      params: expect.objectContaining({ generation_mode: 'fragment', molecule_size: 'uniform_20_30' }),
      standardInputUploads: { protein_pdb: 'protein', fragment_sdf: 'ligand' }
    }))
  })

  it.each(['', '0, 1'])('wraps MOL as SDF and submits docking indices %j', async atoms => {
    await selectModel(LDDM)
    await get('molecule-mode-dock').trigger('click')
    await chooseFragment(structureFile('ligand.mol', molBlock))
    expect(hidden('molecule-size-presets')).toBe(true)
    const input = get('molecule-atoms-to-dock')
    await input.setValue('2')
    expect(blocked()).toBe(true)
    await input.setValue('0 x')
    expect(blocked()).toBe(true)
    await input.setValue(atoms)
    expect(blocked()).toBe(false)
    await submit().trigger('click')
    await flushPromises()
    const uploaded: File | undefined = mocks.upload.mock.calls[0]?.[0]
    expect(uploaded?.name).toBe('ligand.sdf')
    const payload = mocks.submit.mock.calls[0]?.[0]
    expect(payload?.standardInputUploads).toEqual({ protein_pdb: 'protein', fragment_sdf: 'ligand' })
    expect(payload?.params.generation_mode).toBe('dock')
    expect(payload?.params.atoms_to_dock).toBe(atoms || undefined)
  })

  it('accepts PDB fragment/ligand files directly with atom-count preview', async () => {
    await selectModel(LDDM)
    await get('molecule-mode-dock').trigger('click')
    const pdbFile = structureFile('ligand.pdb', 'ATOM      1\nHETATM    2\nEND\n')
    await chooseFragment(pdbFile)
    expect(get('molecule-fragment-preview').text()).toBe('design.molecule.fragmentAtomCount:2:1')
    expect(hidden('molecule-fragment-required')).toBe(true)
    expect(blocked()).toBe(false)
    await submit().trigger('click')
    await flushPromises()
    expect(mocks.upload).toHaveBeenCalledExactlyOnceWith(pdbFile)
    expect(mocks.submit).toHaveBeenCalledWith(expect.objectContaining({
      params: expect.objectContaining({ generation_mode: 'dock' }),
      standardInputUploads: { protein_pdb: 'protein', fragment_sdf: 'ligand' }
    }))
  })

  it('loads offline sample inputs and updates fragment/dock selection via the sketch modal', async () => {
    await selectModel(LDDM)
    await get('molecule-mode-fragment').trigger('click')
    await get('molecule-load-sample').trigger('click')
    await flushPromises()
    expect(get('molecule-fragment-preview').text()).toBe('design.molecule.fragmentAtomCount:13:12')
    expect(blocked()).toBe(false)

    // Open sketch modal in fragment mode and confirm a 2-atom kept subset -> cropped SDF uploaded
    await get('open-fragment-sketch').trigger('click')
    await flushPromises()
    const sketchWrapper = wrapper.findComponent({ name: 'FragmentSketchModal' })
    const subsetFile = structureFile('kept_fragment.sdf', `${molBlock}\r\n$$$$\r\n`)
    sketchWrapper.vm.$emit('confirm', { selectedIndices: [0, 1], exportedFile: subsetFile })
    await flushPromises()
    expect(get('molecule-fragment-cropped').text()).toBe('design.molecule.subsetCroppedTag')
    await submit().trigger('click')
    await flushPromises()
    expect(mocks.upload.mock.calls.some(call => call[0] === subsetFile)).toBe(true)

    // Switch to dock mode and confirm selected indices -> updates atoms_to_dock cleanly
    mocks.upload.mockClear()
    await get('molecule-mode-dock').trigger('click')
    await chooseFragment(structureFile('ligand.sdf', `${molBlock}\r\n$$$$\r\n`))
    await get('open-fragment-sketch').trigger('click')
    await flushPromises()
    wrapper.findComponent({ name: 'FragmentSketchModal' }).vm.$emit('confirm', { selectedIndices: [0, 1], exportedFile: null })
    await flushPromises()
    expect((get('molecule-atoms-to-dock').element as HTMLInputElement).value).toBe('0 1')
  })
})
