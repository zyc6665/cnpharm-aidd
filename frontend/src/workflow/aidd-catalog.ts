import type { WorkflowArtifactSemanticType, WorkflowStepKey } from './artifact-types.ts'
import { WORKFLOW_STEP_KEYS } from './artifact-types.ts'

export interface WorkflowStepCatalogItem {
  readonly key: WorkflowStepKey
  readonly titleKey: string
  readonly descriptionKey: string
  readonly requiredInputTypes: readonly WorkflowArtifactSemanticType[]
  readonly producedOutputTypes: readonly WorkflowArtifactSemanticType[]
  readonly toolSlugs: readonly string[]
  readonly recommendedToolSlug?: string
}

export const AIDD_WORKFLOW_STEP_ORDER: readonly WorkflowStepKey[] = WORKFLOW_STEP_KEYS

export const AIDD_WORKFLOW_STEPS: readonly WorkflowStepCatalogItem[] = [
  {
    key: 'pocketExploration',
    titleKey: 'home.workflow.items.pocketExploration.title',
    descriptionKey: 'home.workflow.items.pocketExploration.description',
    requiredInputTypes: ['protein_pdb'],
    producedOutputTypes: ['pocket_pdb'],
    toolSlugs: ['pocket-explorer'],
    recommendedToolSlug: 'pocket-explorer'
  },
  {
    key: 'moleculeGenerationOrVirtualScreening',
    titleKey: 'home.workflow.items.moleculeGenerationOrVirtualScreening.title',
    descriptionKey: 'home.workflow.items.moleculeGenerationOrVirtualScreening.description',
    requiredInputTypes: ['pocket_pdb'],
    producedOutputTypes: ['generated_ligand'],
    toolSlugs: ['gcdm-pocket-generation', 'targetdiff-service'],
    recommendedToolSlug: 'gcdm-pocket-generation'
  },
  {
    key: 'molecularDockingAndAffinityPrediction',
    titleKey: 'home.workflow.items.molecularDockingAndAffinityPrediction.title',
    descriptionKey: 'home.workflow.items.molecularDockingAndAffinityPrediction.description',
    requiredInputTypes: ['protein_pdb', 'generated_ligand'],
    producedOutputTypes: ['docking_pose', 'affinity_report'],
    toolSlugs: ['molecular-docking'],
    recommendedToolSlug: 'molecular-docking'
  },
  {
    key: 'propertyPrediction',
    titleKey: 'home.workflow.items.propertyPrediction.title',
    descriptionKey: 'home.workflow.items.propertyPrediction.description',
    requiredInputTypes: ['generated_ligand'],
    producedOutputTypes: ['property_report'],
    toolSlugs: ['molp-pc-property-prediction'],
    recommendedToolSlug: 'molp-pc-property-prediction'
  },
  {
    key: 'leadOptimization',
    titleKey: 'home.workflow.items.leadOptimization.title',
    descriptionKey: 'home.workflow.items.leadOptimization.description',
    requiredInputTypes: ['generated_ligand', 'affinity_report', 'property_report'],
    producedOutputTypes: ['optimized_lead'],
    toolSlugs: ['lead-optimizer'],
    recommendedToolSlug: 'lead-optimizer'
  }
]

export const AIDD_WORKFLOW_STEP_MAP: Readonly<Record<WorkflowStepKey, WorkflowStepCatalogItem>> =
  Object.freeze(
    AIDD_WORKFLOW_STEPS.reduce<Record<WorkflowStepKey, WorkflowStepCatalogItem>>(
      (stepMap, step) => {
        stepMap[step.key] = step
        return stepMap
      },
      {} as Record<WorkflowStepKey, WorkflowStepCatalogItem>
    )
  )
