import { computed, reactive } from 'vue'
import { describe, expect, it, vi } from 'vitest'
import type { UploadFile } from 'ant-design-vue'
import type { ArtifactFile, FileUploadResponse, Tool, ToolExample, ToolSchema } from '@/types/models'
import { useToolDetailExamples } from './useToolDetailExamples'

function makeTool(): Tool {
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
  }
}

function makeExample(): ToolExample {
  return {
    name: 'Demo protein',
    params: { threshold: 0.7 },
    input_files: [],
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

function makeArtifactFile(id: string, filename: string): ArtifactFile {
  return {
    id,
    filename,
    content_type: 'chemical/x-pdb',
    size_bytes: 123,
    source_type: 'artifact',
    download_url: `/api/v1/files/${id}/download`,
    task_id: 'task-old',
    task_name: 'Old task',
    tool_id: 'tool-lvpocket',
    tool_name: 'LVpocket',
    tool_slug: 'lvpocket-pocket-prediction',
    created_at: '2026-09-13T00:00:00Z',
  }
}

const flattenedSchema: ToolSchema = {
  type: 'object',
  properties: {
    threshold: { type: 'number', title: 'Threshold' },
    'input_files.protein_pdb': {
      type: 'file',
      format: 'file',
      title: 'Protein PDB',
      _parentKey: 'input_files',
      _originalKey: 'protein_pdb',
    },
  },
  required: ['input_files.protein_pdb'],
}

describe('useToolDetailExamples', () => {
  it('loads and previews example files through injected APIs', async () => {
    const preview = {
      field: 'protein_pdb',
      filename: 'protein.pdb',
      content: 'ATOM',
      truncated: false,
      previewable: true,
    }
    const api = {
      getExample: vi.fn().mockResolvedValue({ data: makeExample() }),
      applyExample: vi.fn(),
      previewFile: vi.fn().mockResolvedValue({ data: preview }),
    }
    const examples = useToolDetailExamples({
      tool: computed(() => makeTool()),
      isLoggedIn: computed(() => true),
      flattenedSchema: computed(() => flattenedSchema),
      formState: reactive<Record<string, unknown>>({}),
      fileList: reactive({}),
      selectedArtifacts: reactive({}),
      exampleFiles: reactive({}),
      convertedFiles: reactive({}),
      api,
      onRequireLogin: vi.fn(),
    })

    await examples.fetchExample('tool-lvpocket')
    await examples.handlePreviewExampleFile('protein_pdb')

    expect(examples.example.value?.name).toBe('Demo protein')
    expect(api.getExample).toHaveBeenCalledWith('tool-lvpocket')
    expect(api.previewFile).toHaveBeenCalledWith('tool-lvpocket', 'protein_pdb')
    expect(examples.previewOpen.value).toBe(true)
    expect(examples.previewLoading.value).toBe(false)
    expect(examples.preview.value).toEqual(preview)
  })

  it('applies example params and files into the run form state', async () => {
    const selectedArtifacts = reactive<Record<string, ArtifactFile | undefined>>({
      'input_files.protein_pdb': makeArtifactFile('artifact-old', 'old.pdb'),
    })
    const convertedFiles = reactive<Record<string, FileUploadResponse | undefined>>({
      'input_files.protein_pdb': makeFileResponse('converted-old', 'old-converted.pdb'),
    })
    const formState = reactive<Record<string, unknown>>({})
    const fileList = reactive<Record<string, UploadFile[]>>({
      'input_files.protein_pdb': [{ uid: 'local-old', name: 'old.pdb' }],
    })
    const exampleFiles = reactive<Record<string, FileUploadResponse | undefined>>({})
    const onExampleLoaded = vi.fn()
    const api = {
      getExample: vi.fn(),
      applyExample: vi.fn().mockResolvedValue({
        data: {
          params: { threshold: 0.7 },
          files: { protein_pdb: makeFileResponse('file-protein', 'protein.pdb') },
        },
      }),
      previewFile: vi.fn(),
    }
    const examples = useToolDetailExamples({
      tool: computed(() => makeTool()),
      isLoggedIn: computed(() => true),
      flattenedSchema: computed(() => flattenedSchema),
      formState,
      fileList,
      selectedArtifacts,
      exampleFiles,
      convertedFiles,
      api,
      onRequireLogin: vi.fn(),
      onExampleLoaded,
    })
    examples.example.value = makeExample()

    await examples.handleUseExample()

    expect(formState.threshold).toBe(0.7)
    expect(formState['input_files.protein_pdb']).toBe('file-protein')
    expect(exampleFiles['input_files.protein_pdb']?.filename).toBe('protein.pdb')
    expect(fileList['input_files.protein_pdb']).toEqual([])
    expect(selectedArtifacts['input_files.protein_pdb']).toBeUndefined()
    expect(convertedFiles['input_files.protein_pdb']).toBeUndefined()
    expect(api.applyExample).toHaveBeenCalledWith('tool-lvpocket')
    expect(onExampleLoaded).toHaveBeenCalled()
    expect(examples.applyingExample.value).toBe(false)
  })
})
