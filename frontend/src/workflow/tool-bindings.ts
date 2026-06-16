import type { WorkflowArtifactSemanticType, WorkflowStepKey } from './artifact-types'

export interface WorkflowToolFieldBinding {
  readonly semanticType: WorkflowArtifactSemanticType
  readonly field: string
  readonly required?: boolean
  readonly preferredArtifactNameIncludes?: readonly string[]
}

type WorkflowToolOutputFileMatch =
  | {
      readonly filenameIncludes: string
      readonly contentType?: string
    }
  | {
      readonly filenameIncludes?: string
      readonly contentType: string
    }

interface WorkflowToolFileOutputExtractor {
  readonly semanticType: WorkflowArtifactSemanticType
  readonly source: 'output_files'
  readonly match: WorkflowToolOutputFileMatch
}

interface WorkflowToolDataOutputExtractor {
  readonly semanticType: WorkflowArtifactSemanticType
  readonly source: 'output_data'
  readonly path: string
}

export type WorkflowToolOutputExtractor =
  | WorkflowToolFileOutputExtractor
  | WorkflowToolDataOutputExtractor

export interface WorkflowToolBindingConfig {
  readonly toolSlug: string
  readonly stepKey: WorkflowStepKey
  readonly acceptedInputTypes: readonly WorkflowArtifactSemanticType[]
  readonly fieldBindings: readonly WorkflowToolFieldBinding[]
  readonly outputExtractors: readonly WorkflowToolOutputExtractor[]
}

export const WORKFLOW_TOOL_BINDINGS = {
  'pocket-explorer': {
    toolSlug: 'pocket-explorer',
    stepKey: 'pocketExploration',
    acceptedInputTypes: ['protein_structure'],
    fieldBindings: [
      {
        semanticType: 'protein_structure',
        field: 'protein_structure',
        required: true
      }
    ],
    outputExtractors: [
      {
        semanticType: 'pocket_structure',
        source: 'output_files',
        match: {
          filenameIncludes: 'pocket'
        }
      }
    ]
  },
  'gcdm-pocket-generation': {
    toolSlug: 'gcdm-pocket-generation',
    stepKey: 'moleculeGenerationOrVirtualScreening',
    acceptedInputTypes: ['pocket_structure'],
    fieldBindings: [
      {
        semanticType: 'pocket_structure',
        field: 'input_files.pocket_pdb',
        required: true,
        preferredArtifactNameIncludes: ['protein_pocket_residues', 'pocket0']
      }
    ],
    outputExtractors: [
      {
        semanticType: 'generated_ligand',
        source: 'output_files',
        match: {
          filenameIncludes: '.sdf'
        }
      }
    ]
  },
  'targetdiff-service': {
    toolSlug: 'targetdiff-service',
    stepKey: 'moleculeGenerationOrVirtualScreening',
    acceptedInputTypes: ['pocket_structure'],
    fieldBindings: [
      {
        semanticType: 'pocket_structure',
        field: 'pocket_structure',
        required: true
      }
    ],
    outputExtractors: [
      {
        semanticType: 'generated_ligand',
        source: 'output_data',
        path: 'outputs.generated_ligands'
      }
    ]
  },
  'molecular-docking': {
    toolSlug: 'molecular-docking',
    stepKey: 'molecularDockingAndAffinityPrediction',
    acceptedInputTypes: ['protein_structure', 'generated_ligand'],
    fieldBindings: [
      {
        semanticType: 'protein_structure',
        field: 'receptor_file',
        required: true
      },
      {
        semanticType: 'generated_ligand',
        field: 'ligand_file',
        required: true
      }
    ],
    outputExtractors: [
      {
        semanticType: 'docking_pose',
        source: 'output_files',
        match: {
          filenameIncludes: 'pose'
        }
      },
      {
        semanticType: 'affinity_report',
        source: 'output_data',
        path: 'outputs.affinity_report'
      }
    ]
  },
  'molp-pc-property-prediction': {
    toolSlug: 'molp-pc-property-prediction',
    stepKey: 'propertyPrediction',
    acceptedInputTypes: ['generated_ligand'],
    fieldBindings: [
      {
        semanticType: 'generated_ligand',
        field: 'smiles_csv',
        required: true
      }
    ],
    outputExtractors: [
      {
        semanticType: 'property_report',
        source: 'output_files',
        match: {
          filenameIncludes: '.csv'
        }
      }
    ]
  },
  'lead-optimizer': {
    toolSlug: 'lead-optimizer',
    stepKey: 'leadOptimization',
    acceptedInputTypes: ['generated_ligand', 'affinity_report', 'property_report'],
    fieldBindings: [
      {
        semanticType: 'generated_ligand',
        field: 'lead_input',
        required: true
      },
      {
        semanticType: 'affinity_report',
        field: 'affinity_report'
      },
      {
        semanticType: 'property_report',
        field: 'property_report'
      }
    ],
    outputExtractors: [
      {
        semanticType: 'optimized_lead',
        source: 'output_files',
        match: {
          filenameIncludes: 'optimized'
        }
      }
    ]
  }
} as const satisfies Readonly<Record<string, WorkflowToolBindingConfig>>

export type WorkflowBoundToolSlug = keyof typeof WORKFLOW_TOOL_BINDINGS
