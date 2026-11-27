import { describe, expect, it } from 'vitest'
import { buildContactRows, downsampleSeries } from './analysis'

describe('MD result chart sampling', () => {
  it('preserves extrema while limiting display samples', () => {
    const rows = Array.from({ length: 2000 }, (_, index) => ({ time_ps: index, rmsd_nm: index === 1001 ? 99 : 1 }))
    const sampled = downsampleSeries(rows, 100, row => row.rmsd_nm)
    expect(sampled.length).toBeLessThanOrEqual(100)
    expect(sampled[0]?.time_ps).toBe(0)
    expect(sampled[sampled.length - 1]?.time_ps).toBe(1999)
    expect(sampled.some(row => row.rmsd_nm === 99)).toBe(true)
  })

  it('parses contacts_csv rows cleanly', () => {
    const contacts = buildContactRows([
      {
        residue_chain: 'A',
        residue_seq: '3',
        residue_icode: '',
        residue_name: 'SER',
        interaction_type: 'hbond_acceptor',
        occupancy: '1.0000',
        contact_frames: '2',
        total_frames: '2',
        min_distance_nm: '0.2783',
        mean_distance_nm: '0.2881'
      },
      { residue_seq: 'invalid', interaction_type: 'vdw_contact' }
    ])
    expect(contacts).toHaveLength(1)
    expect(contacts[0]).toMatchObject({
      residue_chain: 'A',
      residue_seq: 3,
      residue_name: 'SER',
      interaction_type: 'hbond_acceptor',
      occupancy: 1,
      min_distance_nm: 0.2783
    })
  })
})
