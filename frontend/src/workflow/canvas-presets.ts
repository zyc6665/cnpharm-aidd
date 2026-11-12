import type { WorkflowCanvasEdge, WorkflowCanvasNode, WorkflowCanvasPreset } from './canvas-types'

export const FREE_WORKFLOW_CANVAS_PRESET: WorkflowCanvasPreset = {
  id: 'free-canvas',
  kind: 'free',
  nameKey: 'workflow.canvas.freeFlowName',
  descriptionKey: 'workflow.canvas.freeFlowDescription',
  nodes: [],
  edges: []
}

const WORKFLOW_NODE_LIBRARY = {
  inputProtein: {
    id: 'input-protein',
    type: 'input',
    titleKey: 'workflow.nodes.inputProtein.title',
    descriptionKey: 'workflow.nodes.inputProtein.description',
    position: { x: 40, y: 160 },
    producedOutputTypes: ['protein_pdb']
  },
  inputPocket: {
    id: 'input-pocket',
    type: 'input',
    titleKey: 'workflow.nodes.inputPocket.title',
    descriptionKey: 'workflow.nodes.inputPocket.description',
    position: { x: 40, y: 160 },
    producedOutputTypes: ['pocket_pdb']
  },
  inputLigand: {
    id: 'input-ligand',
    type: 'input',
    titleKey: 'workflow.nodes.inputLigand.title',
    descriptionKey: 'workflow.nodes.inputLigand.description',
    position: { x: 40, y: 280 },
    producedOutputTypes: ['ligand_pdb']
  },
  inputGeneratedLigand: {
    id: 'input-generated-ligand',
    type: 'input',
    titleKey: 'workflow.nodes.inputGeneratedLigand.title',
    descriptionKey: 'workflow.nodes.inputGeneratedLigand.description',
    position: { x: 40, y: 160 },
    producedOutputTypes: ['generated_ligand']
  },
  ligandPreparation: {
    id: 'tool-ligand-preparation',
    type: 'tool',
    toolSlugs: ['builtin-ligand-preparation'],
    recommendedToolSlug: 'builtin-ligand-preparation',
    titleKey: 'workflow.nodes.ligandPreparation.title',
    descriptionKey: 'workflow.nodes.ligandPreparation.description',
    position: { x: 300, y: 360 },
    requiredInputTypes: ['ligand_structure@1'],
    producedOutputTypes: ['ligand_structure@1'],
    inputArtifactSlots: [
      { name: 'ligand', type: 'ligand_structure@1', required: true }
    ],
    outputArtifactSlots: [
      { name: 'ligand', type: 'ligand_structure@1', cardinality: 'one', required: true },
      { name: 'report', type: 'run_report@1', cardinality: 'one', required: false }
    ]
  },
  sdfToSmiles: {
    id: 'tool-sdf-to-smiles',
    type: 'tool',
    toolSlugs: ['builtin-sdf-to-smiles-csv'],
    recommendedToolSlug: 'builtin-sdf-to-smiles-csv',
    titleKey: 'workflow.nodes.sdfToSmiles.title',
    descriptionKey: 'workflow.nodes.sdfToSmiles.description',
    position: { x: 560, y: 360 },
    requiredInputTypes: ['ligand_structure@1'],
    producedOutputTypes: ['molecule_table@1'],
    inputArtifactSlots: [
      { name: 'ligand', type: 'ligand_structure@1', required: true }
    ],
    outputArtifactSlots: [
      { name: 'molecules', type: 'molecule_table@1', cardinality: 'one', required: true }
    ]
  },
  rdkitProperties: {
    id: 'tool-rdkit-properties',
    type: 'tool',
    toolSlugs: ['builtin-rdkit-properties'],
    recommendedToolSlug: 'builtin-rdkit-properties',
    titleKey: 'workflow.nodes.rdkitProperties.title',
    descriptionKey: 'workflow.nodes.rdkitProperties.description',
    position: { x: 820, y: 360 },
    requiredInputTypes: ['molecule_table@1'],
    producedOutputTypes: ['molecule_table@1', 'run_report@1'],
    inputArtifactSlots: [
      { name: 'molecules', type: 'molecule_table@1', required: true }
    ],
    outputArtifactSlots: [
      { name: 'properties', type: 'molecule_table@1', cardinality: 'one', required: true },
      { name: 'report', type: 'run_report@1', cardinality: 'one', required: false }
    ]
  },
  molpPcAdmet: {
    id: 'tool-molp-pc-admet',
    type: 'tool',
    toolSlugs: ['molp-pc-property-prediction'],
    recommendedToolSlug: 'molp-pc-property-prediction',
    titleKey: 'workflow.nodes.molpPcAdmet.title',
    descriptionKey: 'workflow.nodes.molpPcAdmet.description',
    position: { x: 1080, y: 360 },
    requiredInputTypes: ['molecule_table@1'],
    producedOutputTypes: ['molecule_table@1', 'run_report@1'],
    inputArtifactSlots: [
      { name: 'molecules', type: 'molecule_table@1', required: true }
    ],
    outputArtifactSlots: [
      { name: 'properties', type: 'molecule_table@1', cardinality: 'one', required: true },
      { name: 'report', type: 'run_report@1', cardinality: 'one', required: true }
    ]
  },
  pocketExploration: {
    id: 'tool-pocket-exploration',
    type: 'tool',
    stepKey: 'pocketExploration',
    toolSlugs: ['lvpocket-pocket-prediction'],
    recommendedToolSlug: 'lvpocket-pocket-prediction',
    titleKey: 'home.workflow.items.pocketExploration.title',
    descriptionKey: 'home.workflow.items.pocketExploration.description',
    position: { x: 280, y: 160 },
    requiredInputTypes: ['protein_pdb'],
    producedOutputTypes: ['pocket_pdb']
  },
  moleculeGeneration: {
    id: 'tool-molecule-generation',
    type: 'tool',
    stepKey: 'moleculeGenerationOrVirtualScreening',
    toolSlugs: ['pocket2mol-pocket-ligand-generation'],
    recommendedToolSlug: 'pocket2mol-pocket-ligand-generation',
    titleKey: 'home.workflow.items.moleculeGenerationOrVirtualScreening.title',
    descriptionKey: 'home.workflow.items.moleculeGenerationOrVirtualScreening.description',
    position: { x: 540, y: 80 },
    requiredInputTypes: ['pocket_pdb'],
    producedOutputTypes: ['generated_ligand']
  },
  docking: {
    id: 'tool-docking',
    type: 'tool',
    stepKey: 'molecularDockingAndAffinityPrediction',
    toolSlugs: ['autodock-vina-docking'],
    recommendedToolSlug: 'autodock-vina-docking',
    titleKey: 'home.workflow.items.molecularDockingAndAffinityPrediction.title',
    descriptionKey: 'home.workflow.items.molecularDockingAndAffinityPrediction.description',
    position: { x: 800, y: 160 },
    requiredInputTypes: ['protein_pdb', 'generated_ligand'],
    producedOutputTypes: ['docking_pose', 'affinity_report']
  },
  propertyPrediction: {
    id: 'tool-property-prediction',
    type: 'tool',
    stepKey: 'propertyPrediction',
    toolSlugs: ['molp-pc-property-prediction'],
    recommendedToolSlug: 'molp-pc-property-prediction',
    titleKey: 'home.workflow.items.propertyPrediction.title',
    descriptionKey: 'home.workflow.items.propertyPrediction.description',
    position: { x: 800, y: 320 },
    requiredInputTypes: ['generated_ligand'],
    producedOutputTypes: ['molecule_table@1', 'run_report@1']
  },
  leadOptimization: {
    // 库中没有部署的“先导化合物优化”工具，占位为人工输入节点，
    // 由用户直接提供 optimized_lead 产物后交给结果汇总。
    id: 'tool-lead-optimization',
    type: 'input',
    titleKey: 'home.workflow.items.leadOptimization.title',
    descriptionKey: 'home.workflow.items.leadOptimization.description',
    position: { x: 1080, y: 240 },
    producedOutputTypes: ['optimized_lead']
  },
  proteinPreparation: {
    id: 'tool-protein-preparation',
    type: 'tool',
    toolSlugs: ['builtin-protein-preparation'],
    recommendedToolSlug: 'builtin-protein-preparation',
    titleKey: 'workflow.nodes.proteinPreparation.title',
    descriptionKey: 'workflow.nodes.proteinPreparation.description',
    position: { x: 280, y: 160 },
    requiredInputTypes: ['protein_structure@1'],
    producedOutputTypes: ['protein_structure@1'],
    inputArtifactSlots: [
      { name: 'protein', type: 'protein_structure@1', required: true }
    ],
    outputArtifactSlots: [
      { name: 'prepared_protein', type: 'protein_structure@1', cardinality: 'one', required: true }
    ]
  },
  mdSimulation: {
    id: 'tool-md-simulation',
    type: 'tool',
    toolSlugs: ['gromacs-md'],
    recommendedToolSlug: 'gromacs-md',
    titleKey: 'workflow.nodes.mdSimulation.title',
    descriptionKey: 'workflow.nodes.mdSimulation.description',
    position: { x: 540, y: 80 },
    requiredInputTypes: ['protein_structure@1'],
    producedOutputTypes: ['md_trajectory@1', 'run_report@1'],
    inputArtifactSlots: [
      { name: 'protein_pdb', type: 'protein_structure@1', required: true }
    ],
    outputArtifactSlots: [
      { name: 'trajectory', type: 'md_trajectory@1', cardinality: 'one', required: true },
      { name: 'report', type: 'run_report@1', cardinality: 'one', required: false }
    ]
  },
  freeEnergy: {
    id: 'tool-free-energy',
    type: 'tool',
    toolSlugs: ['gmx-mmpbsa'],
    recommendedToolSlug: 'gmx-mmpbsa',
    titleKey: 'workflow.nodes.freeEnergy.title',
    descriptionKey: 'workflow.nodes.freeEnergy.description',
    position: { x: 540, y: 260 },
    requiredInputTypes: ['protein_structure@1'],
    producedOutputTypes: ['molecule_table@1', 'run_report@1'],
    inputArtifactSlots: [
      { name: 'protein_pdb', type: 'protein_structure@1', required: true }
    ],
    outputArtifactSlots: [
      { name: 'binding_energy', type: 'molecule_table@1', cardinality: 'one', required: true },
      { name: 'report', type: 'run_report@1', cardinality: 'one', required: false }
    ]
  },
  resultStructure: {
    id: 'result-structure',
    type: 'result',
    titleKey: 'workflow.nodes.resultStructure.title',
    descriptionKey: 'workflow.nodes.resultStructure.description',
    position: { x: 800, y: 160 },
    requiredInputTypes: ['protein_structure@1']
  },
  resultMd: {
    id: 'result-md',
    type: 'result',
    titleKey: 'workflow.nodes.resultMd.title',
    descriptionKey: 'workflow.nodes.resultMd.description',
    position: { x: 800, y: 80 },
    requiredInputTypes: ['md_trajectory@1']
  },
  resultFreeEnergy: {
    id: 'result-free-energy',
    type: 'result',
    titleKey: 'workflow.nodes.resultFreeEnergy.title',
    descriptionKey: 'workflow.nodes.resultFreeEnergy.description',
    position: { x: 800, y: 260 },
    requiredInputTypes: ['molecule_table@1']
  },
  resultSummary: {
    id: 'result-summary',
    type: 'result',
    titleKey: 'workflow.nodes.resultSummary.title',
    descriptionKey: 'workflow.nodes.resultSummary.description',
    position: { x: 1340, y: 240 },
    requiredInputTypes: ['optimized_lead']
  },
  resultPocket: {
    id: 'result-pocket',
    type: 'result',
    titleKey: 'workflow.nodes.resultPocket.title',
    descriptionKey: 'workflow.nodes.resultPocket.description',
    position: { x: 560, y: 160 },
    requiredInputTypes: ['pocket_pdb']
  },
  resultGeneratedLigand: {
    id: 'result-generated-ligand',
    type: 'result',
    titleKey: 'workflow.nodes.resultGeneratedLigand.title',
    descriptionKey: 'workflow.nodes.resultGeneratedLigand.description',
    position: { x: 800, y: 160 },
    requiredInputTypes: ['generated_ligand']
  },
  resultDocking: {
    id: 'result-docking',
    type: 'result',
    titleKey: 'workflow.nodes.resultDocking.title',
    descriptionKey: 'workflow.nodes.resultDocking.description',
    position: { x: 820, y: 200 },
    requiredInputTypes: ['affinity_report']
  },
  resultProperty: {
    id: 'result-property',
    type: 'result',
    titleKey: 'workflow.nodes.resultProperty.title',
    descriptionKey: 'workflow.nodes.resultProperty.description',
    position: { x: 560, y: 160 },
    requiredInputTypes: ['property_report']
  },
  resultAdmet: {
    id: 'result-admet',
    type: 'result',
    titleKey: 'workflow.nodes.resultAdmet.title',
    descriptionKey: 'workflow.nodes.resultAdmet.description',
    position: { x: 1340, y: 360 },
    requiredInputTypes: ['run_report@1']
  }
} as const satisfies Record<string, WorkflowCanvasNode>

function cloneNode(node: WorkflowCanvasNode): WorkflowCanvasNode {
  return {
    ...node,
    position: { ...node.position },
    toolSlugs: node.toolSlugs ? [...node.toolSlugs] : undefined,
    requiredInputTypes: node.requiredInputTypes ? [...node.requiredInputTypes] : undefined,
    producedOutputTypes: node.producedOutputTypes ? [...node.producedOutputTypes] : undefined
  }
}

function createEdge(
  id: string,
  source: string,
  target: string,
  artifactType: WorkflowCanvasEdge['artifactType']
): WorkflowCanvasEdge {
  return { id, source, target, artifactType }
}

function createCanvasPreset(input: {
  id: string
  kind: WorkflowCanvasPreset['kind']
  nameKey: string
  descriptionKey: string
  nodeKeys: Array<keyof typeof WORKFLOW_NODE_LIBRARY>
  edges: WorkflowCanvasEdge[]
}): WorkflowCanvasPreset {
  return {
    id: input.id,
    kind: input.kind,
    nameKey: input.nameKey,
    descriptionKey: input.descriptionKey,
    nodes: input.nodeKeys.map((nodeKey) => cloneNode(WORKFLOW_NODE_LIBRARY[nodeKey])),
    edges: input.edges.map((edge) => ({ ...edge }))
  }
}

export const AIDD_WORKFLOW_CANVAS_PRESET: WorkflowCanvasPreset = createCanvasPreset({
  id: 'aidd-template',
  kind: 'aidd',
  nameKey: 'workflow.canvasPresets.presets.fullPipeline.name',
  descriptionKey: 'workflow.canvasPresets.presets.fullPipeline.description',
  nodeKeys: [
    'inputProtein',
    'pocketExploration',
    'moleculeGeneration',
    'docking',
    'propertyPrediction',
    'leadOptimization',
    'resultSummary'
  ],
  edges: [
    createEdge('edge-input-pocket', 'input-protein', 'tool-pocket-exploration', 'protein_pdb'),
    createEdge('edge-pocket-generation', 'tool-pocket-exploration', 'tool-molecule-generation', 'pocket_pdb'),
    createEdge('edge-input-docking', 'input-protein', 'tool-docking', 'protein_pdb'),
    createEdge('edge-generation-docking', 'tool-molecule-generation', 'tool-docking', 'generated_ligand'),
    createEdge('edge-generation-property', 'tool-molecule-generation', 'tool-property-prediction', 'generated_ligand'),
    createEdge('edge-generation-optimization', 'tool-molecule-generation', 'tool-lead-optimization', 'generated_ligand'),
    createEdge('edge-property-result', 'tool-property-prediction', 'result-summary', 'property_report'),
    createEdge('edge-optimization-result', 'tool-lead-optimization', 'result-summary', 'optimized_lead')
  ]
})

export const PROTEIN_TO_POCKET_CANVAS_PRESET: WorkflowCanvasPreset = createCanvasPreset({
  id: 'protein-pocket-template',
  kind: 'pocket',
  nameKey: 'workflow.canvasPresets.presets.proteinToPocket.name',
  descriptionKey: 'workflow.canvasPresets.presets.proteinToPocket.description',
  nodeKeys: ['inputProtein', 'pocketExploration', 'resultPocket'],
  edges: [
    createEdge('edge-input-pocket-stage', 'input-protein', 'tool-pocket-exploration', 'protein_pdb'),
    createEdge('edge-pocket-result-stage', 'tool-pocket-exploration', 'result-pocket', 'pocket_pdb')
  ]
})

export const POCKET_TO_GENERATION_CANVAS_PRESET: WorkflowCanvasPreset = createCanvasPreset({
  id: 'pocket-generation-template',
  kind: 'screening',
  nameKey: 'workflow.canvasPresets.presets.pocketToGeneration.name',
  descriptionKey: 'workflow.canvasPresets.presets.pocketToGeneration.description',
  nodeKeys: ['inputPocket', 'moleculeGeneration', 'resultGeneratedLigand'],
  edges: [
    createEdge('edge-input-pocket-generation', 'input-pocket', 'tool-molecule-generation', 'pocket_pdb'),
    createEdge('edge-generation-result-stage', 'tool-molecule-generation', 'result-generated-ligand', 'generated_ligand')
  ]
})

export const PROTEIN_LIGAND_TO_DOCKING_CANVAS_PRESET: WorkflowCanvasPreset = createCanvasPreset({
  id: 'protein-ligand-docking-template',
  kind: 'docking',
  nameKey: 'workflow.canvasPresets.presets.proteinLigandToDocking.name',
  descriptionKey: 'workflow.canvasPresets.presets.proteinLigandToDocking.description',
  nodeKeys: ['inputProtein', 'inputGeneratedLigand', 'docking', 'resultDocking'],
  edges: [
    createEdge('edge-protein-docking-stage', 'input-protein', 'tool-docking', 'protein_pdb'),
    createEdge('edge-ligand-docking-stage', 'input-generated-ligand', 'tool-docking', 'generated_ligand'),
    createEdge('edge-docking-result-stage', 'tool-docking', 'result-docking', 'affinity_report')
  ]
})

export const GENERATION_TO_PROPERTY_CANVAS_PRESET: WorkflowCanvasPreset = createCanvasPreset({
  id: 'generation-property-template',
  kind: 'screening',
  nameKey: 'workflow.canvasPresets.presets.generationToProperty.name',
  descriptionKey: 'workflow.canvasPresets.presets.generationToProperty.description',
  nodeKeys: ['inputGeneratedLigand', 'propertyPrediction', 'resultProperty'],
  edges: [
    createEdge('edge-ligand-property-stage', 'input-generated-ligand', 'tool-property-prediction', 'generated_ligand'),
    createEdge('edge-property-result-stage', 'tool-property-prediction', 'result-property', 'property_report')
  ]
})

export const LIGAND_TO_ADMET_CANVAS_PRESET: WorkflowCanvasPreset = createCanvasPreset({
  id: 'ligand-admet-template',
  kind: 'screening',
  nameKey: 'workflow.canvasPresets.presets.ligandToAdmet.name',
  descriptionKey: 'workflow.canvasPresets.presets.ligandToAdmet.description',
  nodeKeys: [
    'inputLigand',
    'ligandPreparation',
    'sdfToSmiles',
    'rdkitProperties',
    'molpPcAdmet',
    'resultAdmet'
  ],
  edges: [
    createEdge('edge-input-ligand-preparation', 'input-ligand', 'tool-ligand-preparation', 'ligand_pdb'),
    createEdge('edge-ligand-smiles', 'tool-ligand-preparation', 'tool-sdf-to-smiles', 'ligand_structure@1'),
    createEdge('edge-smiles-rdkit', 'tool-sdf-to-smiles', 'tool-rdkit-properties', 'molecule_table@1'),
    createEdge('edge-rdkit-molp-pc', 'tool-rdkit-properties', 'tool-molp-pc-admet', 'molecule_table@1'),
    createEdge('edge-molp-pc-admet-result', 'tool-molp-pc-admet', 'result-admet', 'run_report@1')
  ]
})

export const TARGET_PREPARATION_CANVAS_PRESET: WorkflowCanvasPreset = createCanvasPreset({
  id: 'target-preparation-template',
  kind: 'pocket',
  nameKey: 'workflow.canvasPresets.presets.targetPreparation.name',
  descriptionKey: 'workflow.canvasPresets.presets.targetPreparation.description',
  nodeKeys: ['inputProtein', 'proteinPreparation', 'resultStructure'],
  edges: [
    createEdge('edge-input-preparation', 'input-protein', 'tool-protein-preparation', 'protein_pdb'),
    createEdge('edge-preparation-result', 'tool-protein-preparation', 'result-structure', 'protein_pdb')
  ]
})

export const MD_FREE_ENERGY_CANVAS_PRESET: WorkflowCanvasPreset = createCanvasPreset({
  id: 'md-free-energy-template',
  kind: 'dynamics',
  nameKey: 'workflow.canvasPresets.presets.mdFreeEnergy.name',
  descriptionKey: 'workflow.canvasPresets.presets.mdFreeEnergy.description',
  nodeKeys: ['inputProtein', 'proteinPreparation', 'mdSimulation', 'freeEnergy', 'resultMd', 'resultFreeEnergy'],
  edges: [
    createEdge('edge-input-md-preparation', 'input-protein', 'tool-protein-preparation', 'protein_pdb'),
    createEdge('edge-preparation-md', 'tool-protein-preparation', 'tool-md-simulation', 'protein_pdb'),
    createEdge('edge-preparation-free-energy', 'tool-protein-preparation', 'tool-free-energy', 'protein_pdb'),
    createEdge('edge-md-result', 'tool-md-simulation', 'result-md', 'md_trajectory@1'),
    createEdge('edge-free-energy-result', 'tool-free-energy', 'result-free-energy', 'molecule_table@1')
  ]
})

export const WORKFLOW_CANVAS_PRESETS: readonly WorkflowCanvasPreset[] = [
  AIDD_WORKFLOW_CANVAS_PRESET,
  TARGET_PREPARATION_CANVAS_PRESET,
  PROTEIN_TO_POCKET_CANVAS_PRESET,
  POCKET_TO_GENERATION_CANVAS_PRESET,
  PROTEIN_LIGAND_TO_DOCKING_CANVAS_PRESET,
  GENERATION_TO_PROPERTY_CANVAS_PRESET,
  LIGAND_TO_ADMET_CANVAS_PRESET,
  MD_FREE_ENERGY_CANVAS_PRESET
]

export function getWorkflowCanvasPresetById(presetId: string): WorkflowCanvasPreset | null {
  return WORKFLOW_CANVAS_PRESETS.find((preset) => preset.id === presetId) ?? null
}
