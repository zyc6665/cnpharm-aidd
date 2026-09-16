import { describe, expect, it, vi } from 'vitest'
import type { UploadFile } from 'ant-design-vue'
import type { ArtifactFile, FileUploadResponse, ToolSchema } from '@/types/models'
import type { TypedArtifact } from '@/types/artifacts'
import {
  buildToolRunTaskPayload,
  resolveToolRunSubmissionGate,
  resolveToolRunStandardInputs,
  type ToolRunUploadFile,
} from './tool-run-submission'

function makeUploadItem(name: string): UploadFile {
  return {
    uid: `upload-${name}`,
    name,
    originFileObj: { name } as UploadFile['originFileObj'],
  }
}

function makeFileResponse(id: string, filename: string): FileUploadResponse {
  return {
    id,
    filename,
    size_bytes: 123,
    content_type: 'application/octet-stream',
    sha256: 'abc',
  }
}

function makeArtifactFile(overrides: Partial<ArtifactFile> = {}): ArtifactFile {
  return {
    id: 'file-protein',
    filename: 'protein.pdb',
    content_type: 'chemical/x-pdb',
    size_bytes: 123,
    source_type: 'task_output',
    download_url: '/api/v1/files/file-protein/download',
    task_id: 'task-1',
    tool_id: 'tool-1',
    tool_name: 'Protein Tool',
    tool_slug: 'protein-tool',
    created_at: '2026-09-12T00:00:00Z',
    ...overrides,
  }
}

function makeTypedArtifact(overrides: Partial<TypedArtifact> = {}): TypedArtifact {
  return {
    id: 'artifact-1',
    project_id: 'project-1',
    artifact_type: 'molecule_table@1',
    semantic_type: 'molecule_table@1',
    name: 'molecules.csv',
    latest_version: {
      id: 'artifact-version-1',
      version: 1,
      filename: 'molecules.csv',
      content_type: 'text/csv',
      size_bytes: 123,
      sha256: 'abc',
      status: 'available',
      created_at: '2026-09-12T00:00:00Z',
    },
    created_at: '2026-09-12T00:00:00Z',
    updated_at: '2026-09-12T00:00:00Z',
    ...overrides,
  }
}

const concreteSchema: ToolSchema = {
  type: 'object',
  required: ['protein_pdb'],
  properties: {
    protein_pdb: { type: 'file', title: 'Protein PDB', format: 'file' },
    model_choice: { type: 'string', title: 'Model weight', default: 'auto' },
  },
}

describe('tool run submission', () => {
  it('resolves the submission gate before task payload work starts', () => {
    expect(resolveToolRunSubmissionGate({
      isLoggedIn: false,
      toolId: 'tool-lvpocket',
      schema: concreteSchema,
      missingRequiredStandardSlots: [],
    })).toEqual({ status: 'requires_login' })

    expect(resolveToolRunSubmissionGate({
      isLoggedIn: true,
      toolId: undefined,
      schema: concreteSchema,
      missingRequiredStandardSlots: [],
    })).toEqual({ status: 'missing_schema' })

    expect(resolveToolRunSubmissionGate({
      isLoggedIn: true,
      toolId: 'tool-lvpocket',
      schema: concreteSchema,
      missingRequiredStandardSlots: [
        { name: 'protein', type: 'protein_structure@1', required: true },
        { name: 'ligand', type: 'molecule_table@1', required: true },
      ],
    })).toEqual({
      status: 'missing_standard_inputs',
      slotNames: ['protein', 'ligand'],
    })

    expect(resolveToolRunSubmissionGate({
      isLoggedIn: true,
      toolId: 'tool-lvpocket',
      schema: concreteSchema,
      missingRequiredStandardSlots: [],
    })).toEqual({
      status: 'ready',
      toolId: 'tool-lvpocket',
      schema: concreteSchema,
    })
  })

  it('resolves concrete standard input selections before standalone slot state', () => {
    expect(resolveToolRunStandardInputs({
      standardInputSlots: [{ name: 'protein', type: 'protein_structure@1', required: true }],
      standardInputFileFieldBindings: { protein: 'protein_pdb' },
      selectedArtifacts: {
        protein_pdb: makeArtifactFile({ artifact_version_id: 'artifact-version-protein' }),
      },
      uploadedFiles: {
        protein_pdb: {
          fileId: 'file-upload-1',
          filename: 'protein.pdb',
          downloadUrl: '/api/v1/files/file-upload-1/download',
        },
      },
      selectedStandardArtifacts: { protein: makeTypedArtifact() },
      directStandardInputUploads: { protein: 'file-standalone' },
    })).toEqual({
      usesConcreteStandardInputFields: true,
      inputBindings: { protein: 'artifact-version-protein' },
      standardInputUploads: {},
      boundFieldKeys: ['protein_pdb'],
    })
  })

  it('projects concrete file uploads into standard input uploads', async () => {
    const uploadFile = vi.fn<ToolRunUploadFile>().mockResolvedValue(makeFileResponse('file-upload-1', 'protein.pdb'))

    await expect(buildToolRunTaskPayload({
      toolId: 'tool-lvpocket',
      flattenedSchema: concreteSchema,
      formState: { protein_pdb: 'upload-protein.pdb', model_choice: 'auto' },
      fileList: { protein_pdb: [makeUploadItem('protein.pdb')] },
      selectedArtifacts: {},
      standardInputSlots: [{ name: 'protein', type: 'protein_structure@1', required: true }],
      standardInputFileFieldBindings: { protein: 'protein_pdb' },
      selectedStandardArtifacts: {},
      standardInputFileList: {},
      executorType: 'ssh_job',
      uploadFile,
    })).resolves.toEqual({
      tool_id: 'tool-lvpocket',
      params: { params: { model_choice: 'auto' } },
      file_ids: undefined,
      standard_input_uploads: { protein: 'file-upload-1' },
    })
  })

  it('projects selected concrete standard artifacts into input bindings', async () => {
    await expect(buildToolRunTaskPayload({
      toolId: 'tool-lvpocket',
      projectId: 'project-1',
      flattenedSchema: concreteSchema,
      formState: { protein_pdb: 'file-protein', model_choice: 'auto' },
      fileList: {},
      selectedArtifacts: {
        protein_pdb: makeArtifactFile({ artifact_version_id: 'artifact-version-protein' }),
      },
      standardInputSlots: [{ name: 'protein', type: 'protein_structure@1', required: true }],
      standardInputFileFieldBindings: { protein: 'protein_pdb' },
      selectedStandardArtifacts: {},
      standardInputFileList: {},
      executorType: 'ssh_job',
      uploadFile: vi.fn<ToolRunUploadFile>(),
    })).resolves.toEqual({
      tool_id: 'tool-lvpocket',
      project_id: 'project-1',
      params: { params: { model_choice: 'auto' } },
      file_ids: undefined,
      input_bindings: { protein: 'artifact-version-protein' },
    })
  })

  it('keeps standalone standard artifact uploads when no concrete field owns the slot', async () => {
    const uploadFile = vi.fn<ToolRunUploadFile>().mockResolvedValue(makeFileResponse('file-molecules', 'molecules.csv'))

    await expect(buildToolRunTaskPayload({
      toolId: 'tool-molp',
      flattenedSchema: { type: 'object', properties: {}, required: [] },
      formState: {},
      fileList: {},
      selectedArtifacts: {},
      standardInputSlots: [{ name: 'molecules', type: 'molecule_table@1', required: true }],
      standardInputFileFieldBindings: {},
      selectedStandardArtifacts: {},
      standardInputFileList: { molecules: [makeUploadItem('molecules.csv')] },
      executorType: 'ssh_job',
      uploadFile,
    })).resolves.toEqual({
      tool_id: 'tool-molp',
      params: {},
      file_ids: undefined,
      standard_input_uploads: { molecules: 'file-molecules' },
    })
  })

  it('keeps standalone standard artifact selections as input bindings', async () => {
    await expect(buildToolRunTaskPayload({
      toolId: 'tool-molp',
      taskName: 'MolP run',
      projectId: 'project-1',
      flattenedSchema: { type: 'object', properties: {}, required: [] },
      formState: {},
      fileList: {},
      selectedArtifacts: {},
      standardInputSlots: [{ name: 'molecules', type: 'molecule_table@1', required: true }],
      standardInputFileFieldBindings: {},
      selectedStandardArtifacts: { molecules: makeTypedArtifact() },
      standardInputFileList: {},
      executorType: 'ssh_job',
      uploadFile: vi.fn<ToolRunUploadFile>(),
    })).resolves.toEqual({
      name: 'MolP run',
      tool_id: 'tool-molp',
      project_id: 'project-1',
      params: {},
      file_ids: undefined,
      input_bindings: { molecules: 'artifact-version-1' },
    })
  })
})
