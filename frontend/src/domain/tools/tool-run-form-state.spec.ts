import { describe, expect, it } from 'vitest'
import { buildToolRunFormState } from './tool-run-form-state'

describe('tool run form state', () => {
  it('builds concrete file field and standard slot state from one surface description', () => {
    const state = buildToolRunFormState({
      flattenedSchema: {
        type: 'object',
        required: ['protein_pdb'],
        properties: {
          protein_pdb: { type: 'string', format: 'file', title: 'Protein PDB' },
          model_choice: { type: 'string', default: 'auto' },
          device: { type: 'string', default: 'gpu' },
        },
      },
      standardInputSlots: [
        { name: 'protein', type: 'protein_structure@1', required: true },
      ],
    })

    expect(state.formState).toEqual({ model_choice: 'auto', device: 'gpu' })
    expect(state.fileList).toEqual({ protein_pdb: [] })
    expect(state.selectedArtifacts).toEqual({ protein_pdb: undefined })
    expect(state.exampleFiles).toEqual({ protein_pdb: undefined })
    expect(state.convertedFiles).toEqual({ protein_pdb: undefined })
    expect(state.sdfConversionLoading).toEqual({ protein_pdb: false })
    expect(state.sdfConversionErrors).toEqual({ protein_pdb: undefined })
    expect(state.selectedStandardArtifacts).toEqual({ protein: undefined })
    expect(state.standardInputFileList).toEqual({ protein: [] })
  })

  it('keeps draft values while resetting per-file and per-slot records', () => {
    const state = buildToolRunFormState({
      flattenedSchema: {
        type: 'object',
        properties: {
          ligand_pdb: { type: 'file', title: 'Ligand PDB' },
          threshold: { type: 'number', default: 0.5 },
        },
      },
      standardInputSlots: [],
      draft: { threshold: 0.8 },
    })

    expect(state.formState).toEqual({ threshold: 0.8 })
    expect(state.fileList).toEqual({ ligand_pdb: [] })
    expect(state.standardInputFileList).toEqual({})
  })
})
