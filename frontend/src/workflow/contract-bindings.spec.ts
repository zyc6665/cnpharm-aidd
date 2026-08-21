import { describe, expect, it } from 'vitest'
import type { ToolContract } from '@/types/models'
import {
  buildWorkflowToolBindingFromContract,
  deriveArtifactSlotsFromToolContract,
} from './contract-bindings'

function makeToolContract(overrides: Partial<ToolContract> = {}): ToolContract {
  return {
    contract_version: '1.0',
    id: 'tool-1',
    slug: 'lvpocket-pocket-prediction',
    name: 'LVpocket',
    description: null,
    status: 'published',
    is_public: true,
    version: { id: 'version-1', version: '1.0.0', is_active: true, deprecated: false },
    executor: { type: 'tool_package', timeout_sec: null },
    schema: {
      input: { type: 'object', properties: {} },
      output: { type: 'object', properties: {} },
    },
    capability: {
      enabled: true,
      capability: 'lvpocket-pocket-prediction',
      stage: 'lvpocket-pocket-prediction',
      inputs: [
        {
          semantic_type: 'protein_structure@1',
          field: 'protein',
          required: true,
          accepted_extensions: [],
        },
      ],
      outputs: [
        {
          semantic_type: 'binding_pocket@1',
          source: 'artifact',
          match: { type: 'binding_pocket@1', name: 'pocket' },
          path: null,
          required: true,
        },
      ],
      defaults: {},
      virtual: false,
    },
    artifacts: {
      inputs: [{ name: 'protein', type: 'protein_structure@1', required: true }],
      outputs: [
        {
          name: 'pocket',
          type: 'binding_pocket@1',
          cardinality: 'one',
          required: true,
        },
      ],
    },
    validation: { status: 'valid', errors: [] },
    ...overrides,
  }
}

describe('contract artifact slots', () => {
  it('derives named standard artifact slots from Tool Package v2 contracts', () => {
    const slots = deriveArtifactSlotsFromToolContract(makeToolContract())

    expect(slots.inputs).toEqual([
      {
        name: 'protein',
        type: 'protein_structure@1',
        required: true,
      },
    ])
    expect(slots.outputs).toEqual([
      {
        name: 'pocket',
        type: 'binding_pocket@1',
        cardinality: 'one',
        required: true,
      },
    ])
  })

  it('preserves role-aware input requirements from artifact contracts', () => {
    const contract = makeToolContract({
      artifacts: {
        inputs: [
          {
            name: 'protein',
            type: 'protein_structure@1',
            required: true,
            role_preferences: ['prepared_pdb', 'structure_file'],
            required_roles: [],
            readiness_policy: 'prefer_prepared_warn_raw',
            suggested_preparation_tool: 'builtin-protein-preparation',
          },
        ],
        outputs: [],
      },
    })

    const slots = deriveArtifactSlotsFromToolContract(contract)

    expect(slots.inputs[0]).toEqual({
      name: 'protein',
      type: 'protein_structure@1',
      required: true,
      rolePreferences: ['prepared_pdb', 'structure_file'],
      requiredRoles: [],
      readinessPolicy: 'prefer_prepared_warn_raw',
      suggestedPreparationTool: 'builtin-protein-preparation',
    })
  })

  it('preserves provided roles on artifact outputs for workflow auto repair', () => {
    const contract = makeToolContract({
      artifacts: {
        inputs: [],
        outputs: [
          {
            name: 'prepared_protein',
            type: 'protein_structure@1',
            cardinality: 'one',
            required: true,
            provided_roles: ['prepared_pdb', 'receptor_pdbqt'],
          },
        ],
      },
    })

    const slots = deriveArtifactSlotsFromToolContract(contract)

    expect(slots.outputs).toEqual([
      {
        name: 'prepared_protein',
        type: 'protein_structure@1',
        cardinality: 'one',
        required: true,
        providedRoles: ['prepared_pdb', 'receptor_pdbqt'],
      },
    ])
  })

  it('keeps standard artifact refs that are not precompiled into the frontend catalog', () => {
    const contract = makeToolContract({
      artifacts: {
        inputs: [{ name: 'map', type: 'cryoem_map@1', required: true }],
        outputs: [
          {
            name: 'fit_report',
            type: 'model_fit_report@1',
            cardinality: 'one',
            required: true,
          },
        ],
      },
      capability: {
        ...makeToolContract().capability,
        inputs: [{ semantic_type: 'cryoem_map@1', field: 'map', required: true }],
        outputs: [{ semantic_type: 'model_fit_report@1', source: 'artifact', match: { name: 'fit_report' } }],
      },
    })

    const slots = deriveArtifactSlotsFromToolContract(contract)
    const binding = buildWorkflowToolBindingFromContract(contract)

    expect(slots.inputs).toEqual([{ name: 'map', type: 'cryoem_map@1', required: true }])
    expect(slots.outputs).toEqual([
      { name: 'fit_report', type: 'model_fit_report@1', cardinality: 'one', required: true },
    ])
    expect(binding?.acceptedInputTypes).toEqual(['cryoem_map@1'])
    expect(binding?.outputExtractors[0]).toMatchObject({
      semanticType: 'model_fit_report@1',
      source: 'artifact',
      artifactName: 'fit_report',
    })
  })

  it('keeps legacy capability bindings available for existing workflow paths', () => {
    const binding = buildWorkflowToolBindingFromContract(makeToolContract())

    expect(binding?.fieldBindings).toEqual([
      {
        semanticType: 'protein_structure@1',
        field: 'protein',
        required: true,
        acceptedExtensions: [],
      },
    ])
    expect(binding?.outputExtractors[0]).toMatchObject({
      semanticType: 'binding_pocket@1',
      source: 'artifact',
      artifactName: 'pocket',
    })
  })
})
