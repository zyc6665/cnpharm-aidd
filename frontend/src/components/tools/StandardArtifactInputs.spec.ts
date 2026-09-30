import { mount } from '@vue/test-utils'
import type { UploadFile } from 'ant-design-vue'
import { describe, expect, it } from 'vitest'
import type { TypedArtifact } from '@/types/artifacts'
import StandardArtifactInputs from './StandardArtifactInputs.vue'

function makeArtifact(overrides: Partial<TypedArtifact> = {}): TypedArtifact {
  return {
    id: 'artifact-1',
    project_id: 'project-1',
    artifact_type: 'molecule_table',
    semantic_type: 'molecule_table@1',
    standard_type: 'molecule_table',
    standard_version: 1,
    name: 'molecules.csv',
    latest_version: {
      id: 'version-1',
      version: 1,
      filename: 'molecules.csv',
      content_type: 'text/csv',
      size_bytes: 123,
      sha256: 'abc',
      status: 'available',
      created_at: '2026-09-10T00:00:00Z',
    },
    created_at: '2026-09-10T00:00:00Z',
    updated_at: '2026-09-10T00:00:00Z',
    ...overrides,
  }
}

const stubs = {
  ArtifactFilePicker: {
    props: ['accept', 'uploadList'],
    emits: ['update:uploadList'],
    template: '<button type="button" class="artifact-picker" :data-accept="accept" @click="$emit(\'update:uploadList\', [{ name: \'molecules.csv\' }])">pick</button>',
  },
  AFormItem: { props: ['label', 'extra'], template: '<label><span class="label">{{ label }}</span><slot /></label>' },
  ASelect: {
    props: ['value'],
    emits: ['change'],
    template: '<select class="artifact-select" :value="value" @change="$emit(\'change\', $event.target.value)"><slot /></select>',
  },
  ASelectOption: { props: ['value'], template: '<option :value="value"><slot /></option>' },
}

describe('StandardArtifactInputs', () => {
  it('renders direct upload controls without a project context', async () => {
    const wrapper = mount(StandardArtifactInputs, {
      props: {
        slots: [{ name: 'molecules', type: 'molecule_table@1', required: true }],
        currentProjectId: undefined,
        projectArtifacts: [],
        loading: false,
        selectedArtifacts: {},
        uploadLists: {},
        toolId: 'tool-1',
        toolSlug: 'molp-pc',
      },
      global: { stubs },
    })

    expect(wrapper.text()).not.toContain('Tool Package')
    expect(wrapper.text()).not.toContain('molecule_table@1')
    expect(wrapper.find('.artifact-select').exists()).toBe(false)
    expect(wrapper.find('.artifact-picker').attributes('data-accept')).toBe('.csv,.json')

    await wrapper.find('.artifact-picker').trigger('click')

    expect(wrapper.emitted('update-upload-list')).toEqual([
      ['molecules', [{ name: 'molecules.csv' } as UploadFile]],
    ])
  })

  it('renders project file options without exposing contract types', async () => {
    const wrapper = mount(StandardArtifactInputs, {
      props: {
        slots: [{ name: 'molecules', type: 'molecule_table@1', required: true }],
        currentProjectId: 'project-1',
        projectArtifacts: [
          makeArtifact(),
          makeArtifact({
            id: 'artifact-2',
            semantic_type: 'protein_structure@1',
            latest_version: { ...makeArtifact().latest_version, id: 'version-2' },
          }),
        ],
        loading: false,
        selectedArtifacts: { molecules: makeArtifact() },
        uploadLists: { molecules: [] },
        toolId: 'tool-1',
        toolSlug: 'molp-pc',
      },
      global: { stubs },
    })

    expect(wrapper.findAll('option')).toHaveLength(1)
    expect(wrapper.text()).toContain('molecules.csv')
    expect(wrapper.text()).not.toContain('molecule_table@1')

    await wrapper.find('.artifact-select').setValue('version-1')

    expect(wrapper.emitted('select-artifact')).toEqual([['molecules', 'version-1']])
  })
})
