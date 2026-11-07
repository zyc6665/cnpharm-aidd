import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'

function source(path: string): string {
  return readFileSync(resolve(process.cwd(), path), 'utf8')
}

describe('设计流程提交参数与真实工具契约对齐', () => {
  it('结构预测使用 boltz2 的真实采样参数', () => {
    const text = source('src/composables/useStructurePrediction.ts')
    expect(text).toContain('sampling_steps')
    expect(text).toContain('recycling_steps')
    expect(text).toContain('diffusion_samples')
    expect(text).toContain('model_ref')
    expect(text).not.toContain('numRecycles')
    expect(text).not.toContain('useMsa')
  })

  it('分子生成使用 pocket2mol 的 protein_pdb 输入与口袋盒参数', () => {
    const text = source('src/views/design/MoleculeGeneration.vue')
    expect(text).toContain('protein_pdb: selection.structureFileId')
    expect(text).toContain('num_samples')
    expect(text).toContain('center_x')
    expect(text).toContain('center_y')
    expect(text).toContain('center_z')
    expect(text).toContain('pocket_radius')
    expect(text).not.toContain('resolvePocketInputBinding')
    expect(text).not.toContain('num_molecules')
  })

  it('多肽页提交 TheraPainter 的序列预测参数', () => {
    const text = source('src/views/design/PeptideDesign.vue')
    expect(text).toContain('prediction_mode')
    expect(text).toContain('deduplicate')
    expect(text).toContain('batch_size')
    expect(text).toContain('sequence: form.sequence.trim()')
    expect(text).not.toContain('num_peptides')
  })

  it('MD 提交 gromacs-md 的真实参数与 protein_pdb 槽位', () => {
    const mdPage = source('src/views/md/MdSubmit.vue')
    const mdApi = source('src/api/md.ts')
    expect(mdPage).toContain('nsteps')
    expect(mdPage).toContain('box_distance')
    expect(mdPage).toContain('water_model')
    expect(mdPage).not.toContain('force_field')
    expect(mdApi).toContain('protein_pdb: input.complexFileId')
  })

  it('亲和力按模型决定是否要求 sequence，ADMET 设备可配置', () => {
    const text = source('src/views/predict/PropertyPredictSubmit.vue')
    expect(text).toContain('affinityNeedsSequence')
    expect(text).toContain('admetDevice')
  })
})
