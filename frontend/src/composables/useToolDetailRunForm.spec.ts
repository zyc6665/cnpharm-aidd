import { computed } from 'vue'
import { describe, expect, it, vi } from 'vitest'
import type { FileUploadResponse, Tool } from '@/types/models'
import { useToolDetailRunForm } from './useToolDetailRunForm'

function makeTool(config: Record<string, unknown>, overrides: Partial<Tool> = {}): Tool {
  return {
    id: 'tool-lvpocket',
    name: 'LVpocket',
    slug: 'lvpocket-pocket-prediction',
    description: 'Predict protein pockets',
    category: 'AIDD',
    tags: [],
    status: 'published',
    usage_count: 0,
    view_count: 0,
    favorite_count: 0,
    gpu_required: false,
    created_at: '2026-09-13T00:00:00Z',
    current_version: {
      id: 'version-lvpocket',
      tool_id: 'tool-lvpocket',
      version: '2.0.0',
      is_active: true,
      deprecated: false,
      config,
    },
    ...overrides,
  }
}

function makeFileResponse(id: string, filename: string): FileUploadResponse {
  return {
    id,
    filename,
    size_bytes: 123,
    content_type: 'chemical/x-pdb',
    sha256: 'abc',
  }
}

const concreteStandardTool = makeTool({
  type: 'ssh_job',
  input_schema: {
    type: 'object',
    required: ['protein_pdb'],
    properties: {
      protein_pdb: {
        type: 'string',
        format: 'file',
        title: 'Protein PDB',
      },
      model_choice: {
        type: 'string',
        title: 'Model weight',
        default: 'auto',
        enum: ['auto', 'all_scpdb'],
      },
      device: {
        type: 'string',
        title: 'Device',
        default: 'auto',
        enum: ['auto', 'gpu', 'cpu'],
      },
    },
  },
  tool_package_manifest: {
    api_version: 'aidd.sciminer/tool-package',
    kind: 'ToolPackage',
    artifacts: {
      inputs: [{ name: 'protein', type: 'protein_structure@1', required: true }],
      outputs: [],
    },
    parameters_schema: {
      type: 'object',
      properties: {
        model_choice: { type: 'string', default: 'auto' },
      },
      required: [],
    },
  },
})

describe('useToolDetailRunForm', () => {
  it('initializes concrete standard input fields without exposing the standard block', () => {
    const runForm = useToolDetailRunForm({
      tool: computed(() => concreteStandardTool),
      isAuthenticated: computed(() => true),
    })

    runForm.initializeFromSurface()

    expect(runForm.showStandardArtifactInputs.value).toBe(false)
    expect(runForm.standardInputFileFieldBindings.value).toEqual({ protein: 'protein_pdb' })
    expect(runForm.formState.model_choice).toBe('auto')
    expect(runForm.formState.device).toBe('auto')
    expect(runForm.fileList.protein_pdb).toEqual([])
    expect(runForm.selectedArtifacts.protein_pdb).toBeUndefined()
    expect(runForm.missingRequiredStandardSlots.value).toHaveLength(1)

    runForm.fileList.protein_pdb = [{ uid: 'upload-protein', name: 'protein.pdb' }]

    expect(runForm.isFileFieldSatisfied('protein_pdb')).toBe(true)
    expect(runForm.missingRequiredStandardSlots.value).toEqual([])
    expect(runForm.canSubmit.value).toBe(true)
  })

  it('keeps standalone standard uploads separate when no concrete file field owns the slot', () => {
    const tool = makeTool({
      type: 'ssh_job',
      tool_package_manifest: {
        api_version: 'aidd.sciminer/tool-package',
        kind: 'ToolPackage',
        artifacts: {
          inputs: [{ name: 'molecules', type: 'molecule_table@1', required: true }],
          outputs: [],
        },
        parameters_schema: { type: 'object', properties: {}, required: [] },
      },
    })
    const runForm = useToolDetailRunForm({
      tool: computed(() => tool),
      isAuthenticated: computed(() => true),
    })

    runForm.initializeFromSurface()

    expect(runForm.showStandardArtifactInputs.value).toBe(true)
    expect(runForm.standardInputFileFieldBindings.value).toEqual({})
    expect(runForm.missingRequiredStandardSlots.value).toHaveLength(1)

    runForm.updateStandardInputFileList('molecules', [
      { uid: 'upload-molecules', name: 'molecules.csv' },
    ])

    expect(runForm.selectedStandardArtifacts.molecules).toBeUndefined()
    expect(runForm.missingRequiredStandardSlots.value).toEqual([])
  })

  it('converts SDF uploads into ligand PDB file field state', async () => {
    const convert = vi.fn().mockResolvedValue(makeFileResponse('file-ligand-pdb', 'ligand.pdb'))
    const clearFieldValidation = vi.fn()
    const onSuccess = vi.fn()
    const runForm = useToolDetailRunForm({
      tool: computed(() => makeTool({
        type: 'ssh_job',
        input_schema: {
          type: 'object',
          required: ['ligand_pdb'],
          properties: {
            ligand_pdb: { type: 'string', format: 'file', title: 'Ligand PDB' },
          },
        },
      }, { slug: 'msign-affinity-prediction' })),
      isAuthenticated: computed(() => true),
      sdfConversion: {
        convert,
        getErrorMessage: () => 'conversion failed',
        clearFieldValidation,
        onSuccess,
      },
    })
    runForm.initializeFromSurface()

    expect(runForm.showSdfToPdbConverter('ligand_pdb')).toBe(true)

    await runForm.convertSdfToPdbField('ligand_pdb', new File(['sdf'], 'ligand.sdf'))

    expect(convert).toHaveBeenCalledWith(expect.objectContaining({ name: 'ligand.sdf' }))
    expect(runForm.convertedFiles.ligand_pdb?.id).toBe('file-ligand-pdb')
    expect(runForm.fileList.ligand_pdb).toEqual([
      {
        uid: 'converted-file-ligand-pdb',
        name: 'ligand.pdb',
        status: 'done',
        url: '/api/v1/files/file-ligand-pdb/download',
      },
    ])
    expect(runForm.formState.ligand_pdb).toBe('file-ligand-pdb')
    expect(runForm.selectedArtifacts.ligand_pdb).toBeUndefined()
    expect(runForm.exampleFiles.ligand_pdb).toBeUndefined()
    expect(runForm.sdfConversionErrors.ligand_pdb).toBeUndefined()
    expect(runForm.sdfConversionStatusText('ligand_pdb')).toBe('转换成功，已生成 ligand.pdb')
    expect(clearFieldValidation).toHaveBeenCalledWith('ligand_pdb')
    expect(onSuccess).toHaveBeenCalled()
  })
})
