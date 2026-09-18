import type { WorkflowPreflightLabels } from './preflight'

type WorkflowPreflightTranslate = (key: string, params?: Record<string, unknown>) => string

export function buildWorkflowPreflightLabels(t: WorkflowPreflightTranslate): WorkflowPreflightLabels {
  return {
    nodeTitleFallback: t('workflow.preflight.fallback.nodeTitle'),
    sourceNodeFallback: t('workflow.preflight.fallback.sourceNode'),
    filenameFallback: t('workflow.preflight.fallback.filename'),
    toolSlugFallback: t('workflow.preflight.fallback.toolSlug'),
    inputArtifactFallback: t('workflow.preflight.fallback.inputArtifact'),
    invalidArtifactBindingTitle: t('workflow.preflight.issues.invalidArtifactBinding.title'),
    primary: {
      runnableNodes: count => t('workflow.preflight.primary.runnableNodes', { count }),
      missingWorkflowInput: t('workflow.preflight.primary.missingWorkflowInput'),
      invalidToolContract: t('workflow.preflight.primary.invalidToolContract'),
      invalidSemanticEdge: t('workflow.preflight.primary.invalidSemanticEdge'),
      needsPreparationOrConversion: t('workflow.preflight.primary.needsPreparationOrConversion'),
      invalidArtifactBinding: t('workflow.preflight.primary.invalidArtifactBinding'),
      empty: t('workflow.preflight.primary.empty'),
    },
    issues: {
      missing_tool: {
        title: t('workflow.preflight.issues.missingTool.title'),
        detail: () => t('workflow.preflight.issues.missingTool.detail'),
      },
      missing_workflow_input: {
        title: t('workflow.preflight.issues.missingWorkflowInput.title'),
        detail: ({ semanticType }) => t('workflow.preflight.issues.missingWorkflowInput.detail', { semanticType }),
      },
      waiting_upstream: {
        title: t('workflow.preflight.issues.waitingUpstream.title'),
        detail: ({ sourceNodeTitle, semanticType }) => t('workflow.preflight.issues.waitingUpstream.detail', { sourceNodeTitle, semanticType }),
      },
      waiting_input: {
        title: t('workflow.preflight.issues.waitingInput.title'),
        detail: () => t('workflow.preflight.issues.waitingInput.detail'),
      },
      invalid_file_extension: {
        title: t('workflow.preflight.issues.invalidFileExtension.title'),
        detail: ({ filename, semanticType }) => t('workflow.preflight.issues.invalidFileExtension.detail', { filename, semanticType }),
      },
      invalid_semantic_edge: {
        title: t('workflow.preflight.issues.invalidSemanticEdge.title'),
        detail: ({ semanticType }) => t('workflow.preflight.issues.invalidSemanticEdge.detail', { semanticType }),
      },
      invalid_tool_contract: {
        title: t('workflow.preflight.issues.invalidToolContract.title'),
        detail: ({ toolSlug }) => t('workflow.preflight.issues.invalidToolContract.detail', { toolSlug }),
      },
      needs_preparation: {
        title: t('workflow.preflight.issues.needsPreparation.title'),
        detail: () => t('workflow.preflight.issues.needsPreparation.detail'),
      },
      needs_conversion: {
        title: t('workflow.preflight.issues.needsConversion.title'),
        detail: () => t('workflow.preflight.issues.needsConversion.detail'),
      },
      invalid_artifact_binding: {
        title: t('workflow.preflight.issues.invalidArtifactBinding.title'),
        detail: () => t('workflow.preflight.issues.invalidArtifactBinding.detail'),
      },
      running: {
        title: t('workflow.preflight.issues.running.title'),
        detail: () => t('workflow.preflight.issues.running.detail'),
      },
      failed: {
        title: t('workflow.preflight.issues.failed.title'),
        detail: () => t('workflow.preflight.issues.failed.detail'),
      },
      invalidated: {
        title: t('workflow.preflight.issues.invalidated.title'),
        detail: () => t('workflow.preflight.issues.invalidated.detail'),
      },
    },
    savedArtifactBindingMissing: input => t('workflow.preflight.savedBinding.missing', input),
    savedArtifactBindingMismatch: input => t('workflow.preflight.savedBinding.mismatch', input),
    bindingSuggestion: suggestedTool => t('workflow.preflight.binding.suggestion', { suggestedTool }),
    bindingFallbackPreparation: target => t('workflow.preflight.binding.fallbackPreparation', { target }),
    bindingFallbackConversion: target => t('workflow.preflight.binding.fallbackConversion', { target }),
    bindingFallbackInvalid: target => t('workflow.preflight.binding.fallbackInvalid', { target }),
  }
}
