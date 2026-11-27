import { defineComponent } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import MoleculeGeneration from './MoleculeGeneration.vue'
import { MOLECULE_GENERATION_TOOL_SLUG } from '@/types/design'

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
      values && 'count' in values
        ? `${key}:${values.count}:${values.lastIndex}`
        : values && 'fields' in values
          ? `${key}:${values.fields}`
          : key,
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
  props: ['modelValue', 'defaultProjectId', 'projectId', 'hideProjectSelect', 'hidePocketSelect'],
  emits: ['update:modelValue', 'structure-change'],
  setup() { return { pocket } },
  template: '<button data-testid="pick-pocket" @click="$emit(\'update:modelValue\', pocket)">Pick</button>'
})
const ParameterForm = defineComponent({
  props: ['modelValue', 'schema', 'overrides', 'primaryKeys', 'disabled'],
  template: '<div />'
})
const RadioGroup = defineComponent({
  props: ['value', 'disabled', 'size', 'buttonStyle'],
  emits: ['update:value'],
  template: '<fieldset :disabled="disabled" :data-value="value" @click="$emit(\'update:value\', $event.target.value)"><slot /></fieldset>'
})
const RadioButton = defineComponent({ props: ['value'], template: '<button :value="value"><slot /></button>' })
const Upload = defineComponent({ props: ['beforeUpload', 'disabled', 'accept'], template: '<div><slot /></div>' })
const Button = defineComponent({ props: ['type', 'disabled', 'loading', 'size'], template: '<button :disabled="disabled || loading" :data-variant="type"><slot /></button>' })
const Input = defineComponent({
  props: ['value', 'status', 'disabled'],
  emits: ['update:value'],
  template: '<input :value="value" :disabled="disabled" @input="$emit(\'update:value\', $event.target.value)" />'
})
const InputNumber = defineComponent({
  props: ['value', 'disabled', 'step', 'precision', 'placeholder'],
  emits: ['update:value'],
  template: `<input type="number" :value="value ?? ''" :disabled="disabled"
    @input="$emit('update:value', $event.target.value === '' ? null : Number($event.target.value))" />`
})
const Select = defineComponent({
  props: ['value', 'options', 'placeholder', 'disabled'],
  emits: ['update:value'],
  template: `<select :value="value" :disabled="disabled" @change="$emit('update:value', $event.target.value)">
    <option v-for="option in (options || [])" :key="option.value" :value="option.value">{{ option.label }}</option>
  </select>`
})
const Alert = defineComponent({
  props: ['message', 'type', 'description'],
  template: '<div class="alert-stub">{{ message }}<span class="alert-desc">{{ description }}</span><slot name="action" /></div>'
})

const paramStorageKey = (slug: string) => `design:molecule-params:${slug}`

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
        'a-radio-group': RadioGroup, 'a-select': Select, 'a-button': Button, 'a-upload': Upload,
        'a-input': Input, 'a-input-number': InputNumber, 'a-descriptions-item': true, 'a-descriptions': true,
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

async function chooseUpload(testId: string, file: File) {
  const target = wrapper.findAllComponents(Upload).find(w => w.attributes('data-testid') === testId)
  expect(target).toBeDefined()
  const { beforeUpload } = target!.props()
  expect(await beforeUpload(file)).toBe(false)
  await flushPromises()
}

async function chooseFragment(file: File) {
  await chooseUpload('molecule-upload-fragment', file)
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
    expect(wrapper.getComponent(ParameterForm).props('primaryKeys')).toEqual(['temperature', 'num_samples', 'n_samples'])
    expect(wrapper.getComponent(ParameterForm).props('overrides')).toMatchObject({
      generation_mode: { hidden: true }, atoms_to_dock: { hidden: true }, molecule_size: { hidden: true }
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

  it('requires ligand files for fragment mode, hides dock mode card, and clears on de novo or reset', async () => {
    await selectModel(LDDM)
    expect(hidden('molecule-mode-dock')).toBe(true)
    await get('molecule-mode-fragment').trigger('click')
    expect(get('molecule-fragment-required').text()).toBe('design.molecule.fragmentRequired')
    expect(blocked()).toBe(true)
    await submit().trigger('click')
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

  it('wraps MOL as SDF in fragment mode cleanly', async () => {
    await selectModel(LDDM)
    await get('molecule-mode-fragment').trigger('click')
    await chooseFragment(structureFile('ligand.mol', molBlock))
    expect(blocked()).toBe(false)
    await submit().trigger('click')
    await flushPromises()
    const uploaded: File | undefined = mocks.upload.mock.calls[0]?.[0]
    expect(uploaded?.name).toBe('ligand.sdf')
    const payload = mocks.submit.mock.calls[0]?.[0]
    expect(payload?.standardInputUploads).toEqual({ protein_pdb: 'protein', fragment_sdf: 'ligand' })
    expect(payload?.params.generation_mode).toBe('fragment')
  })

  it('accepts PDB fragment/ligand files directly with atom-count preview', async () => {
    await selectModel(LDDM)
    await get('molecule-mode-fragment').trigger('click')
    const pdbFile = structureFile('ligand.pdb', 'ATOM      1\nHETATM    2\nEND\n')
    await chooseFragment(pdbFile)
    expect(get('molecule-fragment-preview').text()).toBe('design.molecule.fragmentAtomCount:2:1')
    expect(hidden('molecule-fragment-required')).toBe(true)
    expect(blocked()).toBe(false)
    await submit().trigger('click')
    await flushPromises()
    expect(mocks.upload).toHaveBeenCalledExactlyOnceWith(pdbFile)
    expect(mocks.submit).toHaveBeenCalledWith(expect.objectContaining({
      params: expect.objectContaining({ generation_mode: 'fragment' }),
      standardInputUploads: { protein_pdb: 'protein', fragment_sdf: 'ligand' }
    }))
  })

  it('loads offline sample inputs and updates fragment selection via the sketch modal', async () => {
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
  })

  it('allows combining a project protein structure with a locally uploaded reference ligand', async () => {
    mocks.resolve.mockImplementation(async slug => ({
      tool: {
        id: slug,
        contract: { artifacts: { inputs: [{ name: 'protein_pdb' }, { name: 'ref_ligand' }] } }
      },
      version: { id: `${slug}-v1` }
    }))

    await selectModel(LDDM)
    wrapper.findComponent(PocketPicker).vm.$emit('structure-change', {
      projectId: 'project',
      targetId: 't1',
      proteinId: 'pr1',
      structureId: 's1',
      structureFileId: 'protein-from-project',
      structureUrn: 'file:receptor.pdb'
    })
    await get('molecule-pocket-mode-ligand').trigger('click')
    const refLigand = structureFile('ref.sdf', `${molBlock}\r\n$$$$\r\n`)
    await chooseUpload('molecule-upload-ref-ligand', refLigand)
    await submit().trigger('click')
    await flushPromises()

    expect(mocks.upload).toHaveBeenCalledExactlyOnceWith(refLigand)
    expect(mocks.submit).toHaveBeenCalledWith(expect.objectContaining({
      projectId: 'project',
      standardInputUploads: { protein_pdb: 'protein', ref_ligand: 'ligand' }
    }))
  })

  it('builds contextPreviewScene with both receptor and ligand entries when fragment uploaded', async () => {
    await selectModel(LDDM)
    await get('molecule-mode-fragment').trigger('click')
    const ligandFile = structureFile('ligand.sdf', `${molBlock}\r\n$$$$\r\n`)
    await chooseFragment(ligandFile)
    await flushPromises()

    // MoleculeDesignContextPanel is not stubbed, so we can find it and check its scene prop
    const contextPanel = wrapper.findComponent({ name: 'MoleculeDesignContextPanel' })
    expect(contextPanel.exists()).toBe(true)

    const scene = contextPanel.props('previewScene')
    expect(scene).toBeTruthy()
    expect(scene.entries).toHaveLength(2)

    const ligandEntry = scene.entries.find((e: any) => e.role === 'ligand')
    const receptorEntry = scene.entries.find((e: any) => e.role === 'receptor')

    expect(ligandEntry).toBeTruthy()
    expect(ligandEntry.format).toBe('sdf')
    expect(ligandEntry.source).toBe('input')
    expect(ligandEntry.url).toMatch(/^blob:/)

    expect(receptorEntry).toBeTruthy()
    expect(receptorEntry.format).toBe('pdb')
    expect(receptorEntry.source).toBe('input')
    expect(receptorEntry.url).toContain('/api/v1/files/')
  })

  it('updates contextPreviewScene when fragment is cropped to subset', async () => {
    await selectModel(LDDM)
    await get('molecule-mode-fragment').trigger('click')
    await chooseFragment(structureFile('ligand.sdf', `${molBlock}\r\n$$$$\r\n`))
    await flushPromises()

    const contextPanel = wrapper.findComponent({ name: 'MoleculeDesignContextPanel' })
    const beforeScene = contextPanel.props('previewScene')
    const beforeLigandKey = beforeScene?.entries.find((e: any) => e.role === 'ligand')?.key

    await get('open-fragment-sketch').trigger('click')
    await flushPromises()
    const subsetFile = structureFile('cropped.sdf', `${molBlock}\r\n$$$$\r\n`)
    wrapper.findComponent({ name: 'FragmentSketchModal' }).vm.$emit('confirm', { selectedIndices: [0, 1], exportedFile: subsetFile })
    await flushPromises()

    const afterScene = contextPanel.props('previewScene')
    const afterLigandEntry = afterScene?.entries.find((e: any) => e.role === 'ligand')

    expect(afterLigandEntry).toBeTruthy()
    expect(afterLigandEntry.key).not.toBe(beforeLigandKey)
    expect(afterLigandEntry.label).toBe('cropped.sdf')
    expect(afterScene?.entries).toHaveLength(2)
  })

  it('supports manual center coordinates and co-crystal HETATM extraction in upload mode', async () => {
    await get('molecule-source-mode').get('button[value="upload"]').trigger('click')
    await get('molecule-upload-project').setValue('project')
    const complexPdb = structureFile(
      'complex.pdb',
      [
        'ATOM      1  CA  ALA A   1      30.000  40.000  50.000  1.00  0.00           C',
        'HETATM    2  C1  LIG A 201      10.000  20.000  30.000  1.00  0.00           C',
        'HETATM    3  N1  LIG A 201      14.000  24.000  34.000  1.00  0.00           N',
        'END'
      ].join('\n')
    )
    await chooseUpload('molecule-upload-structure', complexPdb)
    expect(wrapper.find(byId('molecule-hetatm-banner')).exists()).toBe(true)
    await get('molecule-use-hetatm-center').trigger('click')
    await flushPromises()

    expect((get('molecule-center-x').element as HTMLInputElement).value).toBe('12')
    expect((get('molecule-center-y').element as HTMLInputElement).value).toBe('22')
    expect((get('molecule-center-z').element as HTMLInputElement).value).toBe('32')
    expect(blocked()).toBe(false)

    await get('molecule-center-x').setValue('15.5')
    await flushPromises()
    await submit().trigger('click')
    await flushPromises()

    expect(mocks.upload).toHaveBeenCalledExactlyOnceWith(complexPdb)
    expect(mocks.submit).toHaveBeenCalledWith(
      expect.objectContaining({
        params: expect.objectContaining({ center_x: 15.5, center_y: 22, center_z: 32 }),
        standardInputUploads: { protein_pdb: 'ligand' }
      })
    )
  })

  it('supports defining the pocket with a reference ligand on LDDM and derives center on Pocket2Mol', async () => {
    mocks.resolve.mockImplementation(async slug => ({
      tool: {
        id: slug,
        contract:
          slug === LDDM
            ? { artifacts: { inputs: [{ name: 'protein_pdb' }, { name: 'ref_ligand' }] } }
            : { artifacts: { inputs: [{ name: 'protein_pdb' }] } }
      },
      version: { id: `${slug}-v1` }
    }))

    await selectModel(LDDM)
    await get('molecule-source-mode').get('button[value="upload"]').trigger('click')
    await get('molecule-upload-project').setValue('project')
    const protein = structureFile('receptor.pdb', 'ATOM      1  CA  GLY A   1      1.000  2.000  3.000  1.00  0.00           C\nEND\n')
    const refLigand = structureFile(
      'ref.sdf',
      [
        'Ref',
        '  RDKit          3D',
        '',
        '  2  1  0  0  0  0  0  0  0  0999 V2000',
        '   10.0000   20.0000   30.0000 C   0  0  0  0  0  0  0  0  0  0  0  0',
        '   14.0000   26.0000   38.0000 O   0  0  0  0  0  0  0  0  0  0  0  0',
        '  1  2  1  0',
        'M  END',
        '$$$$',
        ''
      ].join('\n')
    )
    await chooseUpload('molecule-upload-structure', protein)
    await chooseUpload('molecule-upload-ref-ligand', refLigand)

    expect(get('molecule-ref-ligand-summary').text()).toContain('design.molecule.refLigandParsed')
    expect(blocked()).toBe(false)

    // Previews both receptor and reference ligand in context panel in denovo mode
    const contextPanel = wrapper.findComponent({ name: 'MoleculeDesignContextPanel' })
    const scene = contextPanel.props('previewScene')
    expect(scene?.entries.some((e: any) => e.role === 'receptor')).toBe(true)
    expect(scene?.entries.some((e: any) => e.role === 'ligand')).toBe(true)

    await submit().trigger('click')
    await flushPromises()
    expect(mocks.upload).toHaveBeenCalledTimes(2)
    expect(mocks.submit).toHaveBeenCalledWith(
      expect.objectContaining({
        toolId: LDDM,
        params: expect.objectContaining({ center_x: 12, center_y: 23, center_z: 34 }),
        standardInputUploads: { protein_pdb: 'ligand', ref_ligand: 'ligand' }
      })
    )

    // Switching to Pocket2Mol falls back to passing derived center without unsupported ref_ligand slot
    mocks.upload.mockClear()
    mocks.submit.mockClear()
    await selectModel(POCKET2MOL)
    await submit().trigger('click')
    await flushPromises()
    expect(mocks.upload).toHaveBeenCalledTimes(1)
    expect(mocks.submit).toHaveBeenCalledWith(
      expect.objectContaining({
        toolId: POCKET2MOL,
        params: expect.objectContaining({ center_x: 12, center_y: 23, center_z: 34 }),
        standardInputUploads: { protein_pdb: 'ligand' }
      })
    )
  })

  it('clears upload-derived center coords on switching back to project mode and uploads pocket slot when supported', async () => {
    mocks.resolve.mockImplementation(async slug => ({
      tool: {
        id: slug,
        contract: { artifacts: { inputs: [{ name: 'protein_pdb' }, { name: 'pocket' }] } }
      },
      version: { id: `${slug}-v1` }
    }))

    await selectModel(LDDM)
    await get('molecule-source-mode').get('button[value="upload"]').trigger('click')
    const complexPdb = structureFile(
      'complex.pdb',
      [
        'HETATM    1  C1  LIG A 201      10.000  20.000  30.000  1.00  0.00           C',
        'HETATM    2  N1  LIG A 201      14.000  24.000  34.000  1.00  0.00           N',
        'END'
      ].join('\n')
    )
    await chooseUpload('molecule-upload-structure', complexPdb)
    await get('molecule-use-hetatm-center').trigger('click')
    await flushPromises()

    expect((get('molecule-center-x').element as HTMLInputElement).value).toBe('12')

    // Switching back to project restores selected project pocket and clears upload-derived center
    await get('molecule-source-mode').get('button[value="project"]').trigger('click')
    await flushPromises()
    expect(wrapper.find(byId('molecule-hetatm-banner')).exists()).toBe(false)
    await get('molecule-pocket-mode-coords').trigger('click')
    await flushPromises()
    expect((get('molecule-center-x').element as HTMLInputElement).value).toBe('')

    // Unreadable ref ligand does not keep phantom filename selected
    await get('molecule-pocket-mode-ligand').trigger('click')
    await chooseUpload('molecule-upload-ref-ligand', structureFile('broken.sdf', 'not-a-ligand'))
    expect(wrapper.find(byId('molecule-upload-ref-ligand-name')).exists()).toBe(false)

    // Pocket PDB mode uploads the pocket file to uploads.pocket when tool contract declares pocket
    await get('molecule-pocket-mode-file').trigger('click')
    const pocketFile = structureFile(
      'pocket0.pdb',
      'HETATM    1  C1  UNL A   1       3.000   4.000   5.000  1.00  0.00           C\nEND\n'
    )
    await chooseUpload('molecule-upload-pocket', pocketFile)
    await submit().trigger('click')
    await flushPromises()

    expect(mocks.upload).toHaveBeenCalledExactlyOnceWith(pocketFile)
    expect(mocks.submit).toHaveBeenCalledWith(
      expect.objectContaining({
        standardInputUploads: { protein_pdb: 'protein', pocket: 'ligand' }
      })
    )
  })

  it('announces restored parameters and resets them to schema defaults', async () => {
    wrapper.unmount()
    localStorage.setItem(
      paramStorageKey(MOLECULE_GENERATION_TOOL_SLUG),
      JSON.stringify({ sourceMode: 'project', uploadProjectId: '', params: { num_samples: 42 } })
    )

    wrapper = mountPage()
    await flushPromises()

    expect(get('params-restored-hint').text()).toContain('design.molecule.paramsRestoredDiff:num_samples')
    expect(wrapper.getComponent(ParameterForm).props('modelValue')).toMatchObject({ num_samples: 42 })

    await get('params-restored-reset').trigger('click')
    await flushPromises()

    expect(hidden('params-restored-hint')).toBe(true)
    expect(wrapper.getComponent(ParameterForm).props('modelValue')).toMatchObject({ num_samples: 20 })
    expect(localStorage.getItem(paramStorageKey(MOLECULE_GENERATION_TOOL_SLUG))).toBeNull()
  })

  it('stays quiet when nothing was restored or restored values match defaults', async () => {
    expect(hidden('params-restored-hint')).toBe(true)

    wrapper.unmount()
    localStorage.setItem(
      paramStorageKey(MOLECULE_GENERATION_TOOL_SLUG),
      JSON.stringify({ sourceMode: 'project', uploadProjectId: '', params: { num_samples: 20 } })
    )

    wrapper = mountPage()
    await flushPromises()

    expect(hidden('params-restored-hint')).toBe(true)
  })
})
