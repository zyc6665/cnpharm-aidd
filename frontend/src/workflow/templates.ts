import type { WorkflowTemplate } from './template-types'

export const AIDD_WORKFLOW_TEMPLATE: WorkflowTemplate = {
  id: 'aidd-template',
  kind: 'aidd',
  nameKey: 'workflow.templates.aidd.name',
  descriptionKey: 'workflow.templates.aidd.description',
  nodes: [
    {
      id: 'input-protein',
      type: 'input',
      titleKey: 'workflow.nodes.inputProtein.title',
      descriptionKey: 'workflow.nodes.inputProtein.description',
      position: { x: 40, y: 160 },
      producedOutputTypes: ['protein_pdb']
    },
    {
      id: 'tool-pocket-exploration',
      type: 'tool',
      stepKey: 'pocketExploration',
      toolSlugs: ['pocket-explorer'],
      recommendedToolSlug: 'pocket-explorer',
      titleKey: 'home.workflow.items.pocketExploration.title',
      descriptionKey: 'home.workflow.items.pocketExploration.description',
      position: { x: 280, y: 160 },
      requiredInputTypes: ['protein_pdb'],
      producedOutputTypes: ['pocket_pdb']
    },
    {
      id: 'tool-molecule-generation',
      type: 'tool',
      stepKey: 'moleculeGenerationOrVirtualScreening',
      toolSlugs: ['gcdm-pocket-generation', 'targetdiff-service'],
      recommendedToolSlug: 'gcdm-pocket-generation',
      titleKey: 'home.workflow.items.moleculeGenerationOrVirtualScreening.title',
      descriptionKey: 'home.workflow.items.moleculeGenerationOrVirtualScreening.description',
      position: { x: 540, y: 80 },
      requiredInputTypes: ['pocket_pdb'],
      producedOutputTypes: ['generated_ligand']
    },
    {
      id: 'tool-docking',
      type: 'tool',
      stepKey: 'molecularDockingAndAffinityPrediction',
      toolSlugs: ['molecular-docking'],
      recommendedToolSlug: 'molecular-docking',
      titleKey: 'home.workflow.items.molecularDockingAndAffinityPrediction.title',
      descriptionKey: 'home.workflow.items.molecularDockingAndAffinityPrediction.description',
      position: { x: 800, y: 160 },
      requiredInputTypes: ['protein_pdb', 'generated_ligand'],
      producedOutputTypes: ['docking_pose', 'affinity_report']
    },
    {
      id: 'tool-property-prediction',
      type: 'tool',
      stepKey: 'propertyPrediction',
      toolSlugs: ['molp-pc-property-prediction'],
      recommendedToolSlug: 'molp-pc-property-prediction',
      titleKey: 'home.workflow.items.propertyPrediction.title',
      descriptionKey: 'home.workflow.items.propertyPrediction.description',
      position: { x: 800, y: 320 },
      requiredInputTypes: ['generated_ligand'],
      producedOutputTypes: ['property_report']
    },
    {
      id: 'tool-lead-optimization',
      type: 'tool',
      stepKey: 'leadOptimization',
      toolSlugs: ['lead-optimizer'],
      recommendedToolSlug: 'lead-optimizer',
      titleKey: 'home.workflow.items.leadOptimization.title',
      descriptionKey: 'home.workflow.items.leadOptimization.description',
      position: { x: 1080, y: 240 },
      requiredInputTypes: ['generated_ligand', 'affinity_report', 'property_report'],
      producedOutputTypes: ['optimized_lead']
    },
    {
      id: 'result-summary',
      type: 'result',
      titleKey: 'workflow.nodes.resultSummary.title',
      descriptionKey: 'workflow.nodes.resultSummary.description',
      position: { x: 1340, y: 240 },
      requiredInputTypes: ['optimized_lead']
    }
  ],
  edges: [
    {
      id: 'edge-input-pocket',
      source: 'input-protein',
      target: 'tool-pocket-exploration',
      artifactType: 'protein_pdb'
    },
    {
      id: 'edge-pocket-generation',
      source: 'tool-pocket-exploration',
      target: 'tool-molecule-generation',
      artifactType: 'pocket_pdb'
    },
    {
      id: 'edge-input-docking',
      source: 'input-protein',
      target: 'tool-docking',
      artifactType: 'protein_pdb'
    },
    {
      id: 'edge-generation-docking',
      source: 'tool-molecule-generation',
      target: 'tool-docking',
      artifactType: 'generated_ligand'
    },
    {
      id: 'edge-generation-property',
      source: 'tool-molecule-generation',
      target: 'tool-property-prediction',
      artifactType: 'generated_ligand'
    },
    {
      id: 'edge-docking-optimization',
      source: 'tool-docking',
      target: 'tool-lead-optimization',
      artifactType: 'affinity_report'
    },
    {
      id: 'edge-property-optimization',
      source: 'tool-property-prediction',
      target: 'tool-lead-optimization',
      artifactType: 'property_report'
    },
    {
      id: 'edge-optimization-result',
      source: 'tool-lead-optimization',
      target: 'result-summary',
      artifactType: 'optimized_lead'
    }
  ]
}

export const WORKFLOW_TEMPLATES: readonly WorkflowTemplate[] = [
  AIDD_WORKFLOW_TEMPLATE
]

export function getWorkflowTemplateById(templateId: string): WorkflowTemplate | null {
  return WORKFLOW_TEMPLATES.find(template => template.id === templateId) ?? null
}
