import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

describe('DockingResultDetail source contract', () => {
  const source = readFileSync(resolve(process.cwd(), 'src/views/screening/DockingResultDetail.vue'), 'utf8')

  it('keeps the required viewer surface and pose navigation', () => {
    expect(source).toContain('<MoleculeViewer v-if="scene" :scene="scene" mode="docking"')
    expect(source).toContain('screening.detail.nextPose')
  })

  it('shows missing metrics explicitly while keeping valid zeros', () => {
    expect(source).toContain("t('screening.detail.notProvided')")
    expect(source).toContain('Number.isFinite(value) ? String(value)')
    // 缺失值不能靠 falsy 判断（会把 0 误判为空）
    expect(source).not.toContain('value ? String(value)')
  })

  it('describes Vina RMSD bounds relative to the best pose of the same run', () => {
    expect(source).toContain("t('screening.detail.hints.rmsd')")
    expect(source).toContain('rmsd_lb: rmsdLbIdx >= 0')
  })

  it('overrides the shared hint color for dark-theme contrast', () => {
    expect(source).toContain(':deep(.app-description-hint)')
    expect(source).toContain('var(--theme-text-secondary')
  })
})
