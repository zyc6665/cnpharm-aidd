import { describe, expect, it } from 'vitest'
import { buildPredictDistributionGroups } from './predict-distribution'
import { ADMET_DETAIL_PROFILE, AFFINITY_DETAIL_PROFILE } from './predictDetailProfiles'
import type { CsvPreviewColumn } from '@/domain/tasks/csv-result'

function column(key: string): CsvPreviewColumn {
  return { key, originalKey: key, title: key }
}

describe('buildPredictDistributionGroups', () => {
  it('按吸收/分布/代谢等 ADMET 分组归类指标，并保留未归类列', () => {
    const columns = [
      column('F20'),
      column('HIA'),
      column('BBB'),
      column('CYP1A2 inhibitor'),
      column('hERG'),
      column('novel_metric')
    ]

    const groups = buildPredictDistributionGroups(ADMET_DETAIL_PROFILE, columns)

    expect(groups.map(group => group.titleKey)).toEqual([
      'predict.result.detailSectionAbsorption',
      'predict.result.detailSectionDistribution',
      'predict.result.detailSectionMetabolism',
      'predict.result.detailSectionToxicity',
      'predict.result.distributionOther'
    ])
    expect(groups[0]!.columns.map(item => item.key)).toEqual(['F20', 'HIA'])
    expect(groups[4]!.columns.map(item => item.key)).toEqual(['novel_metric'])
  })

  it('亲和力按亲和力预测与结构预处理分组', () => {
    const columns = [
      column('prediction.predicted_affinity'),
      column('prediction.predicted_ligand_to_pocket'),
      column('preprocessing.pocket_atom_count')
    ]

    const groups = buildPredictDistributionGroups(AFFINITY_DETAIL_PROFILE, columns)

    expect(groups.map(group => group.titleKey)).toEqual([
      'predict.result.detailSectionAffinityPrediction',
      'predict.result.detailSectionAffinityPreprocessing'
    ])
  })

  it('没有匹配分组时回退到全部指标', () => {
    const groups = buildPredictDistributionGroups(
      { ...ADMET_DETAIL_PROFILE, basic: null, sections: [] },
      [column('foo'), column('bar')]
    )

    expect(groups).toEqual([
      {
        titleKey: 'predict.result.distributionAll',
        columns: [expect.objectContaining({ key: 'foo' }), expect.objectContaining({ key: 'bar' })]
      }
    ])
  })
})
