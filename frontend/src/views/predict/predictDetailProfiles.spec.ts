import { describe, expect, it } from 'vitest'
import {
  ADMET_DETAIL_PROFILE,
  AFFINITY_DETAIL_PROFILE,
  GENERIC_DETAIL_PROFILE,
  resolvePredictDetailProfile
} from './predictDetailProfiles'

describe('predictDetailProfiles', () => {
  it('groups ADMET models under the ADMET profile', () => {
    expect(resolvePredictDetailProfile('admet_prediction')).toBe(ADMET_DETAIL_PROFILE)
    expect(ADMET_DETAIL_PROFILE.showSmiles).toBe(true)
    expect(ADMET_DETAIL_PROFILE.showRadar).toBe(true)
  })

  it('groups all affinity models under the affinity profile', () => {
    expect(resolvePredictDetailProfile('affinity')).toBe(AFFINITY_DETAIL_PROFILE)
    expect(AFFINITY_DETAIL_PROFILE.showSmiles).toBe(false)
    expect(AFFINITY_DETAIL_PROFILE.showRadar).toBe(false)
    expect(AFFINITY_DETAIL_PROFILE.sections.map(section => section.titleKey)).toContain(
      'predict.result.detailSectionAffinityPrediction'
    )
  })

  it('falls back to the generic profile for unknown/new model families', () => {
    const profile = resolvePredictDetailProfile('brand_new_family')
    expect(profile.generic).toBe(true)
    expect(profile.key).toBe('brand_new_family')
    expect(profile.sections).toEqual(GENERIC_DETAIL_PROFILE.sections)
  })
})
