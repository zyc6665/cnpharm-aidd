import { describe, it, expect } from 'vitest'
import zh from '@/locales/zh-CN'
import en from '@/locales/en-US'

function get(obj: unknown, path: string): unknown {
  return path.split('.').reduce<unknown>((acc, key) => {
    if (acc && typeof acc === 'object') return (acc as Record<string, unknown>)[key]
    return undefined
  }, obj)
}

const REQUIRED_KEYS = [
  'nav.structurePredict',
  'nav.pocketPredict',
  'nav.designPipeline',
  'design.pipeline.title',
  'design.pipeline.stage.structure',
  'design.upstream.missingStructure',
  'design.upstream.missingPocket',
  'design.runs.continueFlow',
  'design.runs.nextStep',
  'workflow.guided.noProtein',
  'targets.predict.timeout',
  'targets.structure.pocketsTimeout',
]

describe('new design-pipeline i18n keys exist in both locales', () => {
  for (const path of REQUIRED_KEYS) {
    it(path, () => {
      expect(get(zh, path)).toBeTruthy()
      expect(get(en, path)).toBeTruthy()
    })
  }
})
