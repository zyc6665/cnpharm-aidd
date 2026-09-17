import { test } from 'vitest'
import assert from 'node:assert/strict'

import type { ToolContract, WorkbenchGroupTool } from '../src/types/models.d.ts'
import type { WorkflowArtifact, WorkflowTaskRef } from '../src/workflow/artifact-types.ts'
import {
  buildWorkflowPreflightReport,
  buildWorkflowToolBindingFromContract,
  resolveWorkflowToolBinding,
} from '../src/workflow/contract-bindings.ts'
import { extractArtifactsFromTaskResultWithBinding } from '../src/workflow/artifact-resolver.ts'

function createContract(): ToolContract {
  return {
    contract_version: '1.0',
    id: 'tool-dynamic',
    slug: 'dynamic-pocket-generator',
    name: 'Dynamic Pocket Generator',
    description: 'Generate ligands from a pocket',
    status: 'published',
    is_public: true,
    version: {
      id: 'version-dynamic',
      version: '1.0.0',
      is_active: true,
      deprecated: false
    },
    executor: {
      type: 'ssh_job',
      timeout_sec: 3600
    },
    schema: {
      input: {
        type: 'object',
        properties: {
          input_files: {
            type: 'object',
            properties: {
              pocket: { type: 'string', format: 'uri' }
            }
          }
        }
      },
      output: {
        type: 'object',
        properties: {
          success: { type: 'boolean' }
        }
      }
    },
    capability: {
      enabled: true,
      capability: 'molecule_generation',
      stage: 'molecule_generation',
      inputs: [
        {
          semantic_type: 'binding_pocket@1',
          field: 'input_files.pocket',
          required: true,
          accepted_extensions: ['.pdb']
        }
      ],
      outputs: [
        {
          semantic_type: 'ligand_structure@1',
          source: 'artifact',
          match: {
            type: 'ligand_structure@1'
          },
          required: true
        }
      ],
      defaults: {
        'params.n_samples': 8
      },
      virtual: false
    },
    validation: {
      status: 'valid',
      errors: []
    },
    artifacts: {
      inputs: [{ name: 'pocket', type: 'binding_pocket@1', required: true }],
      outputs: [
        {
          name: 'generated_ligands',
          type: 'ligand_structure@1',
          cardinality: 'many',
          required: true
        }
      ]
    }
  }
}

function createTool(contract: ToolContract): WorkbenchGroupTool {
  return {
    id: 'tool-dynamic',
    slug: contract.slug,
    name: contract.name,
    description: contract.description,
    status: 'published',
    is_public: true,
    is_recommended: false,
    sort_order: 0,
    contract
  }
}

function createArtifact(input: Partial<WorkflowArtifact> = {}): WorkflowArtifact {
  return {
    id: input.id ?? 'artifact-pocket',
    semanticType: input.semanticType ?? 'binding_pocket@1',
    name: input.name ?? 'protein_pocket_residues.pdb',
    stepKey: input.stepKey ?? 'pocketExploration',
    toolSlug: input.toolSlug ?? 'lvpocket-pocket-prediction',
    fileId: input.fileId ?? 'file-pocket',
    createdAt: input.createdAt ?? '2026-06-17T10:00:00Z'
  }
}

function createTask(): WorkflowTaskRef {
  return {
    id: 'task-dynamic',
    name: 'Dynamic generation',
    tool_id: 'tool-dynamic',
    tool_slug: 'dynamic-pocket-generator',
    status: 'success',
    progress: 100,
    output_files: [
      {
        id: 'file-generated',
        original_name: 'generated_ligands.sdf',
        filename: 'generated_ligands.sdf',
        content_type: 'chemical/x-mdl-sdfile',
        url: '/api/v1/files/file-generated/download'
      }
    ],
    output_data: {
      standard_artifacts: {
        artifact_version_ids_by_ref: {
          generated_ligands: 'artifact-version-generated'
        },
        file_ids_by_artifact_ref: {
          generated_ligands: ['file-generated']
        }
      }
    },
    finished_at: '2026-06-17T11:00:00Z',
    created_at: '2026-06-17T10:00:00Z'
  }
}

test('应从 ToolContract 生成工作流输入绑定和输出提取规则', async () => {
  const binding = buildWorkflowToolBindingFromContract(createContract())

  assert.equal(binding?.toolSlug, 'dynamic-pocket-generator')
  assert.equal(binding?.stepKey, 'moleculeGenerationOrVirtualScreening')
  assert.deepEqual(binding?.acceptedInputTypes, ['binding_pocket@1'])
  assert.deepEqual(binding?.fieldBindings, [
    {
      semanticType: 'binding_pocket@1',
      field: 'input_files.pocket',
      required: true,
      acceptedExtensions: ['.pdb']
    }
  ])
  assert.equal(binding?.outputExtractors[0]?.semanticType, 'ligand_structure@1')
  assert.equal(binding?.outputExtractors[0]?.source, 'artifact')
})

test('动态工作台工具只能使用 embedded contract 生成绑定', async () => {
  const binding = resolveWorkflowToolBinding(createTool(createContract()))

  assert.equal(binding?.toolSlug, 'dynamic-pocket-generator')
  assert.equal(binding?.fieldBindings[0]?.semanticType, 'binding_pocket@1')
  assert.equal(
    resolveWorkflowToolBinding({
      ...createTool(createContract()),
      slug: 'legacy-tool-without-contract',
      contract: undefined
    }),
    null
  )
})

test('预检报告应展示已匹配输入和预期输出', async () => {
  const binding = buildWorkflowToolBindingFromContract(createContract())

  assert.ok(binding)

  const report = buildWorkflowPreflightReport({
    binding,
    artifacts: [createArtifact()]
  })

  assert.equal(report.ready, true)
  assert.equal(report.inputs[0]?.field, 'input_files.pocket')
  assert.equal(report.inputs[0]?.artifact?.id, 'artifact-pocket')
  assert.deepEqual(report.expectedOutputs, ['ligand_structure@1'])
})

test('动态 contract 输出提取器应能从任务结果生成语义产物', async () => {
  const binding = buildWorkflowToolBindingFromContract(createContract())

  assert.ok(binding)

  const artifacts = extractArtifactsFromTaskResultWithBinding({
    stepKey: 'moleculeGenerationOrVirtualScreening',
    binding,
    task: createTask()
  })

  assert.equal(artifacts.length, 1)
  assert.equal(artifacts[0]?.semanticType, 'ligand_structure@1')
  assert.equal(artifacts[0]?.fileId, 'file-generated')
  assert.equal(artifacts[0]?.metadata?.source, 'standard_artifacts')
})
