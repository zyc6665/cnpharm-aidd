import { test } from 'vitest'
import assert from 'node:assert/strict'

import {
  AIDD_WORKFLOW_CANVAS_PRESET,
  GENERATION_TO_PROPERTY_CANVAS_PRESET,
  PUBCHEM_TO_ADMET_CANVAS_PRESET,
  POCKET_TO_GENERATION_CANVAS_PRESET,
  PROTEIN_LIGAND_TO_DOCKING_CANVAS_PRESET,
  PROTEIN_TO_POCKET_CANVAS_PRESET,
  WORKFLOW_CANVAS_PRESETS,
  getWorkflowCanvasPresetById
} from '../src/workflow/canvas-presets.ts'

test('AIDD workflow template defines a connected node graph', () => {
  assert.equal(AIDD_WORKFLOW_CANVAS_PRESET.id, 'aidd-template')
  assert.equal(AIDD_WORKFLOW_CANVAS_PRESET.nodes.length >= 7, true)

  const nodeTypes = new Set(AIDD_WORKFLOW_CANVAS_PRESET.nodes.map(node => node.type))
  assert.equal(nodeTypes.has('input'), true)
  assert.equal(nodeTypes.has('tool'), true)
  assert.equal(nodeTypes.has('result'), true)

  const nodeIds = new Set(AIDD_WORKFLOW_CANVAS_PRESET.nodes.map(node => node.id))
  for (const edge of AIDD_WORKFLOW_CANVAS_PRESET.edges) {
    assert.equal(nodeIds.has(edge.source), true, `missing source node ${edge.source}`)
    assert.equal(nodeIds.has(edge.target), true, `missing target node ${edge.target}`)
  }

  assert.equal(AIDD_WORKFLOW_CANVAS_PRESET.nodes.some(node => node.position.x > 0), true)
  assert.equal(AIDD_WORKFLOW_CANVAS_PRESET.nodes.some(node => node.position.y > 0), true)
})

test('workflow templates can be resolved by id', () => {
  assert.equal(WORKFLOW_CANVAS_PRESETS.includes(AIDD_WORKFLOW_CANVAS_PRESET), true)
  assert.equal(getWorkflowCanvasPresetById('aidd-template'), AIDD_WORKFLOW_CANVAS_PRESET)
  assert.equal(getWorkflowCanvasPresetById('protein-pocket-template'), PROTEIN_TO_POCKET_CANVAS_PRESET)
  assert.equal(getWorkflowCanvasPresetById('pocket-generation-template'), POCKET_TO_GENERATION_CANVAS_PRESET)
  assert.equal(getWorkflowCanvasPresetById('protein-ligand-docking-template'), PROTEIN_LIGAND_TO_DOCKING_CANVAS_PRESET)
  assert.equal(getWorkflowCanvasPresetById('generation-property-template'), GENERATION_TO_PROPERTY_CANVAS_PRESET)
  assert.equal(getWorkflowCanvasPresetById('pubchem-admet-template'), PUBCHEM_TO_ADMET_CANVAS_PRESET)
  assert.equal(getWorkflowCanvasPresetById('missing-template'), null)
})

test('workflow templates include stage-oriented researcher presets', () => {
  const canvasPresetIds = new Set(WORKFLOW_CANVAS_PRESETS.map((template) => template.id))

  for (const canvasPresetId of [
    'protein-pocket-template',
    'pocket-generation-template',
    'protein-ligand-docking-template',
    'generation-property-template',
    'pubchem-admet-template'
  ]) {
    assert.equal(canvasPresetIds.has(canvasPresetId), true, `missing ${canvasPresetId}`)
  }
})

test('PubChem to ADMET preset follows AT-003 delivery chain', () => {
  assert.equal(PUBCHEM_TO_ADMET_CANVAS_PRESET.id, 'pubchem-admet-template')

  const nodesById = new Map(PUBCHEM_TO_ADMET_CANVAS_PRESET.nodes.map((node) => [node.id, node]))
  assert.equal(nodesById.get('tool-fetch-pubchem')?.recommendedToolSlug, 'builtin-fetch-ligand')
  assert.equal(nodesById.get('tool-ligand-preparation')?.recommendedToolSlug, 'ligand-preparation')
  assert.equal(nodesById.get('tool-sdf-to-smiles')?.recommendedToolSlug, 'builtin-sdf-to-smiles-csv')
  assert.equal(nodesById.get('tool-rdkit-properties')?.recommendedToolSlug, 'builtin-rdkit-properties')
  assert.equal(nodesById.get('tool-molp-pc-admet')?.recommendedToolSlug, 'molp-pc-property-prediction')

  assert.deepEqual(
    PUBCHEM_TO_ADMET_CANVAS_PRESET.edges.map((edge) => [edge.source, edge.target, edge.artifactType]),
    [
      ['tool-fetch-pubchem', 'tool-ligand-preparation', 'ligand_structure@1'],
      ['tool-ligand-preparation', 'tool-sdf-to-smiles', 'ligand_structure@1'],
      ['tool-sdf-to-smiles', 'tool-rdkit-properties', 'molecule_table@1'],
      ['tool-rdkit-properties', 'tool-molp-pc-admet', 'molecule_table@1'],
      ['tool-molp-pc-admet', 'result-admet', 'run_report@1']
    ]
  )
})
