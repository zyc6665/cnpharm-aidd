import { test } from 'vitest'
import assert from 'node:assert/strict'
import {
  buildAgentCapabilityConfig,
  createAgentCapabilityInputForm,
  createAgentCapabilityOutputForm,
  isAgentCapabilityFormComplete,
  parseAgentCapabilityForm
} from './agent-capability'

test('旧 Agent 语义映射默认输入输出行保持创建页约定', () => {
  assert.deepEqual(createAgentCapabilityInputForm(), {
    semantic_type: '',
    field: '',
    accepted_extensions: ''
  })
  assert.deepEqual(createAgentCapabilityOutputForm(), {
    semantic_type: '',
    source: 'output_files',
    path: '',
    match_extension: '',
    filename_contains_any: '',
    required: true
  })
})

test('旧 Agent config 可解析回表单并保护默认字段', () => {
  const parsed = parseAgentCapabilityForm({
    agent_capability: {
      enabled: true,
      capability: 'molecule_generation',
      inputs: [
        { semantic_type: 'protein_pdb@1', accepted_extensions: ['.pdb', '.ent'] },
        'bad-item'
      ],
      outputs: [
        {
          semantic_type: 'ligand_sdf@1',
          source: 'output_data',
          path: 'result.ligand',
          required: false,
          match: { extension: '.sdf', filename_contains_any: ['ligand', 'sample'] }
        }
      ],
      defaults: { n_samples: 8 }
    }
  })

  assert.equal(parsed.enabled, true)
  assert.equal(parsed.capability, 'molecule_generation')
  assert.equal(parsed.stage, 'molecule_generation')
  assert.equal(parsed.defaultsText, '{\n  "n_samples": 8\n}')
  assert.deepEqual(parsed.inputs, [
    { semantic_type: 'protein_pdb@1', field: 'protein_pdb@1', accepted_extensions: '.pdb,.ent' }
  ])
  assert.deepEqual(parsed.outputs, [
    {
      semantic_type: 'ligand_sdf@1',
      source: 'output_data',
      path: 'result.ligand',
      match_extension: '.sdf',
      filename_contains_any: 'ligand,sample',
      required: false
    }
  ])
})

test('缺少旧 Agent config 时返回关闭状态', () => {
  assert.deepEqual(parseAgentCapabilityForm({}), {
    enabled: false,
    capability: 'molecule_generation',
    stage: 'molecule_generation',
    defaultsText: '{}',
    inputs: [],
    outputs: []
  })
})

test('旧 Agent 表单完整性和提交 config 组装保持兼容结构', () => {
  const form = {
    enabled: true,
    capability: ' molecule_generation ',
    stage: ' ',
    inputs: [
      { semantic_type: ' protein_pdb@1 ', field: ' ', accepted_extensions: ' .pdb, .ent ' },
      createAgentCapabilityInputForm()
    ],
    outputs: [
      {
        semantic_type: ' ligand_sdf@1 ',
        source: 'output_files' as const,
        path: ' output/ligands.sdf ',
        match_extension: ' .sdf ',
        filename_contains_any: ' ligand, sample ',
        required: true
      }
    ]
  }

  assert.equal(isAgentCapabilityFormComplete(form), true)
  assert.deepEqual(buildAgentCapabilityConfig(form, { n_samples: 8 }), {
    enabled: true,
    capability: 'molecule_generation',
    stage: 'molecule_generation',
    inputs: [
      {
        semantic_type: 'protein_pdb@1',
        field: 'protein_pdb@1',
        accepted_extensions: ['.pdb', '.ent']
      }
    ],
    outputs: [
      {
        semantic_type: 'ligand_sdf@1',
        source: 'output_files',
        path: 'output/ligands.sdf',
        required: true,
        match: { extension: '.sdf', filename_contains_any: ['ligand', 'sample'] }
      }
    ],
    defaults: { n_samples: 8 }
  })
})

test('旧 Agent 表单未开启时不生成 config，开启但缺少输入输出时不完整', () => {
  const disabled = {
    enabled: false,
    capability: 'molecule_generation',
    stage: '',
    inputs: [],
    outputs: []
  }

  assert.equal(isAgentCapabilityFormComplete(disabled), true)
  assert.equal(buildAgentCapabilityConfig(disabled, {}), undefined)
  assert.equal(isAgentCapabilityFormComplete({ ...disabled, enabled: true }), false)
})
