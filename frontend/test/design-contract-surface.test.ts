import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

function source(path: string): string {
  return readFileSync(resolve(process.cwd(), path), 'utf8')
}

describe('设计流程参数按选中模型动态渲染', () => {
  it('结构预测使用模型 schema，并隐藏后端注入的 sequence', () => {
    const composable = source('src/composables/useStructurePrediction.ts')
    const form = source('src/components/design/StructurePredictForm.vue')
    expect(composable).toContain('normalizeParameters')
    expect(composable).toContain('buildDefaultValues')
    expect(composable).toContain("STRUCTURE_HIDDEN_PARAMS = ['sequence', 'seq_length']")
    expect(form).toContain('ModelParameterForm')
    expect(form).toContain('selectedOption?.parameterSchema')
    expect(form).not.toContain('numRecycles')
    expect(form).not.toContain('useMsa')
  })

  it('分子生成使用 pocket2mol 的 protein_pdb 输入与口袋中心注入', () => {
    const text = source('src/views/design/MoleculeGeneration.vue')
    expect(text).toContain('protein_pdb: selection.structureFileId')
    expect(text).toContain('ModelParameterForm')
    expect(text).toContain('selectedOption?.parameterSchema')
    expect(text).toContain('center_x: toNumber')
    expect(text).toContain('center_y: toNumber')
    expect(text).toContain('center_z: toNumber')
    expect(text).not.toContain('resolvePocketInputBinding')
    expect(text).not.toContain('num_molecules')
  })

  it('多肽页使用 TheraPainter 的模型 schema', () => {
    const text = source('src/views/design/PeptideDesign.vue')
    expect(text).toContain('ModelParameterForm')
    expect(text).toContain('selectedOption?.parameterSchema')
    expect(text).toContain('normalizeParameters')
    expect(text).not.toContain('num_peptides')
    expect(text).not.toContain('PocketPicker')
  })

  it('MD 使用 gromacs-md 的模型 schema 与 protein_pdb 槽位', () => {
    const mdPage = source('src/views/md/MdSubmit.vue')
    const mdApi = source('src/api/md.ts')
    expect(mdPage).toContain('ModelParameterForm')
    expect(mdPage).toContain('selectedOption?.parameterSchema')
    expect(mdPage).not.toContain('force_field')
    expect(mdApi).toContain('protein_pdb: input.complexFileId')
  })

  it('亲和力与 ADMET 参数由模型 schema 决定', () => {
    const text = source('src/views/predict/PropertyPredictSubmit.vue')
    expect(text).toContain('admetSchema')
    expect(text).toContain('affinitySchema')
    expect(text).toContain('ModelParameterForm')
    expect(text).toContain('normalizeParameters')
    expect(text).not.toContain('affinityNeedsSequence')
  })
})
