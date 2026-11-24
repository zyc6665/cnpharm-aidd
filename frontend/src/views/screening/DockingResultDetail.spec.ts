import { describe, expect, it } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

describe('DockingResultDetail source contract', () => {
  it('keeps the required viewer surface and pose navigation', () => {
    const source = readFileSync(resolve(process.cwd(), 'src/views/screening/DockingResultDetail.vue'), 'utf8')
    expect(source).toContain('<MoleculeViewer v-if="scene" :scene="scene" mode="docking"')
    expect(source).toContain('screening.detail.nextPose')
  })
})
