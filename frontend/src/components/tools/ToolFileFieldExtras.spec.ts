import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import ToolFileFieldExtras from './ToolFileFieldExtras.vue'
import type { FileUploadResponse, SchemaProperty } from '@/types/models'
import i18n from '@/locales'

const fileProperty: SchemaProperty = { type: 'string', format: 'file', title: 'Protein PDB' }
const exampleFile: FileUploadResponse = { id: 'example-1', filename: 'example.pdb' }
const convertedFile: FileUploadResponse = { id: 'converted-1', filename: 'converted.pdb' }

describe('ToolFileFieldExtras', () => {
  const stubs = {
    FileTextOutlined: { template: '<i />' },
    AButton: {
      emits: ['click'],
      template: '<button type="button" @click="$emit(\'click\')"><slot /></button>',
    },
    AUpload: {
      props: ['beforeUpload'],
      template: '<div class="upload-stub" @click="beforeUpload({ name: \'ligand.sdf\' })"><slot /></div>',
    },
  }

  it('renders SDF conversion and file bindings for file fields', async () => {
    const beforeUpload = vi.fn(() => false)
    const wrapper = mount(ToolFileFieldExtras, {
      props: {
        fieldKey: 'ligand_pdb',
        property: fileProperty,
        showSdfConverter: true,
        sdfConversionLoading: false,
        sdfConversionStatusText: '转换失败',
        sdfConversionError: 'bad sdf',
        exampleFile,
        convertedFile,
        createSdfUploadBefore: () => beforeUpload,
      },
      global: { plugins: [i18n], stubs },
    })

    expect(wrapper.text()).toContain('SDF 转 Ligand PDB')
    expect(wrapper.text()).toContain('转换失败')
    expect(wrapper.find('.sdf-converter-status').classes()).toContain('is-error')
    expect(wrapper.text()).toContain('example.pdb')
    expect(wrapper.text()).toContain('converted.pdb')

    await wrapper.find('.upload-stub').trigger('click')
    await wrapper.find('[data-testid="clear-example-file"]').trigger('click')
    await wrapper.find('[data-testid="clear-converted-file"]').trigger('click')

    expect(beforeUpload).toHaveBeenCalledWith({ name: 'ligand.sdf' })
    expect(wrapper.emitted('clear-example')).toEqual([['ligand_pdb']])
    expect(wrapper.emitted('clear-converted')).toEqual([['ligand_pdb']])
  })

  it('omits file bindings for non-file fields', () => {
    const wrapper = mount(ToolFileFieldExtras, {
      props: {
        fieldKey: 'model_choice',
        property: { type: 'string', title: 'Model weight' },
        showSdfConverter: false,
        sdfConversionLoading: false,
        sdfConversionStatusText: '',
        sdfConversionError: undefined,
        exampleFile,
        convertedFile,
        createSdfUploadBefore: () => () => false,
      },
      global: { plugins: [i18n], stubs },
    })

    expect(wrapper.find('.sdf-converter').exists()).toBe(false)
    expect(wrapper.find('.example-file-binding').exists()).toBe(false)
    expect(wrapper.find('.converted-file-binding').exists()).toBe(false)
  })
})
